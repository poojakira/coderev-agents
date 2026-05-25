"""QLoRA fine-tuning of CodeLlama-7B on code review data using Unsloth + TRL.

Fixes applied:
  A1-001 — all four RNG surfaces seeded before any model or data ops
  A1-002 — git hash, dataset fingerprint, hardware logged to W&B
  A1-003 — print() replaced with structlog
  A1-005 — train/eval split added; SFTConfig updated with eval_strategy
  A2-006 — dataset pinned to revision (operator must set commit SHA)
  A4-001 — Pandera schema validation before processing
  A4-002 — Arrow cache hash logged to W&B for supply-chain traceability
  A4-003 — PII redaction before training ingestion
  ABSENT-A4 — lineage recorded for every transformation step
"""

import json
import platform
import random
import subprocess
from pathlib import Path

import numpy as np
import structlog
import torch
import wandb
from datasets import load_dataset
from transformers import set_seed as hf_set_seed
from trl import SFTConfig, SFTTrainer
from unsloth import FastLanguageModel

from coderev.config import Settings
from coderev.training.data_schema import CodeReviewSchema
from coderev.training.lineage import record_transform
from coderev.training.pii_redaction import redact_dataset_row

import pandera as pa

logger = structlog.get_logger()
settings = Settings()

TRAIN_CONFIG = {
    "base_model": "codellama/CodeLlama-7b-Instruct-hf",
    "lora_r": 32,
    "lora_alpha": 64,
    "lora_dropout": 0.05,
    "max_seq_length": 2048,
    "per_device_train_batch_size": 4,
    "gradient_accumulation_steps": 4,
    "num_train_epochs": 3,
    "learning_rate": 2e-4,
    "warmup_ratio": 0.05,
    "lr_scheduler_type": "cosine",
    "weight_decay": 0.01,
    "bf16": True,
    "seed": 42,
    # Operator MUST replace "main" with a pinned commit SHA from HuggingFace Hub.
    # Retrieve from: https://huggingface.co/datasets/JetBrains/code-review/commits/main
    # Fix A2-006.
    "dataset_revision": "main",  # UNVERIFIED: replace with commit SHA
}


def format_review_example(example: dict) -> str:
    """Format a code review example into instruction format."""
    return (
        "### Instruction:\nReview this code change for bugs, security issues, and style.\n\n"
        f"### Input:\n```\n{example['diff']}\n```\n\n"
        f"### Response:\n{example['review']}"
    )


def _hash_hf_cache(ds) -> str:
    """SHA-256 over all Arrow files backing a HuggingFace dataset split.

    Fix A4-002: detects tampered or substituted cache files.
    """
    import hashlib
    h = hashlib.sha256()
    cache_files = ds.cache_files
    if not cache_files:
        return "no-cache-files"
    for entry in sorted(cache_files, key=lambda e: e["filename"]):
        p = Path(entry["filename"])
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def load_training_data(
    dataset_name: str = "JetBrains/code-review",
    dataset_revision: str = TRAIN_CONFIG["dataset_revision"],
) -> tuple:
    """Load, validate, redact, and split the code review dataset.

    Order of operations is fixed:
    1. Load from Hub (pinned revision)
    2. Hash Arrow cache (supply-chain integrity)
    3. Schema validation (structural contract)
    4. PII redaction (privacy)
    5. Train/eval split (must precede any learned transforms)
    6. Format (stateless — safe after split)
    """
    import pandas as pd
    from datasets import Dataset as HFDataset

    ds = load_dataset(dataset_name, split="train", revision=dataset_revision)

    # A4-002: log cache hash for supply-chain traceability
    cache_hash = _hash_hf_cache(ds)
    logger.info("dataset_cache_hash", sha256=cache_hash, revision=dataset_revision)

    # A4-001: validate schema before any processing
    df = ds.to_pandas()[["diff", "review"]].copy()
    try:
        validated_df = CodeReviewSchema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        logger.error(
            "dataset_schema_validation_failed",
            failure_count=len(exc.failure_cases),
            sample_failures=exc.failure_cases.to_dict(orient="records")[:5],
        )
        raise RuntimeError(
            f"Dataset schema validation failed with {len(exc.failure_cases)} violations. "
            "Aborting to prevent a corrupted training run."
        ) from exc

    # Filter after validation
    validated_df = validated_df[
        (validated_df["diff"].str.len() > 50) & (validated_df["review"].str.len() > 20)
    ]
    ds_clean = HFDataset.from_pandas(validated_df, preserve_index=False)

    record_transform(
        step_name="schema_validation",
        input_fingerprint=ds._fingerprint,
        output_fingerprint=ds_clean._fingerprint,
        parameters={"dataset": dataset_name, "revision": dataset_revision},
        row_count_in=len(ds),
        row_count_out=len(ds_clean),
    )

    # A4-003: PII redaction before split so eval set is also clean
    ds_redacted = ds_clean.map(redact_dataset_row, with_indices=True, desc="PII redaction")
    pii_rows = sum(1 for r in ds_redacted if r.get("_pii_findings"))
    logger.info("pii_redaction_complete", rows_with_pii=pii_rows, total_rows=len(ds_redacted))

    record_transform(
        step_name="pii_redaction",
        input_fingerprint=ds_clean._fingerprint,
        output_fingerprint=ds_redacted._fingerprint,
        parameters={"patterns": ["EMAIL", "PHONE", "IPV4", "API_KEY", "AWS_KEY", "JWT", "GITHUB_PAT", "HF_TOKEN"]},
        row_count_in=len(ds_clean),
        row_count_out=len(ds_redacted),
    )

    # A1-005: split BEFORE formatting — ordering must precede any learned transform
    split = ds_redacted.train_test_split(test_size=0.05, seed=TRAIN_CONFIG["seed"])
    train_ds = split["train"].map(lambda x: {"text": format_review_example(x)})
    eval_ds = split["test"].map(lambda x: {"text": format_review_example(x)})

    record_transform(
        step_name="train_test_split",
        input_fingerprint=ds_redacted._fingerprint,
        output_fingerprint=f"train:{train_ds._fingerprint}|eval:{eval_ds._fingerprint}",
        parameters={"test_size": 0.05, "seed": TRAIN_CONFIG["seed"]},
        row_count_in=len(ds_redacted),
        row_count_out=len(train_ds) + len(eval_ds),
    )

    logger.info(
        "dataset_loaded",
        train_size=len(train_ds),
        eval_size=len(eval_ds),
        train_fingerprint=train_ds._fingerprint,
        eval_fingerprint=eval_ds._fingerprint,
        cache_hash=cache_hash,
    )
    return train_ds, eval_ds, cache_hash


def train():
    """Run QLoRA fine-tuning with full reproducibility controls and W&B tracking."""
    # A1-001: set ALL RNG surfaces before any model or data operations
    _seed = TRAIN_CONFIG["seed"]
    random.seed(_seed)
    np.random.seed(_seed)
    torch.manual_seed(_seed)
    torch.cuda.manual_seed_all(_seed)
    hf_set_seed(_seed)  # covers transformers, datasets, evaluate

    # Collect run metadata for W&B
    _git_hash = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    _gpu_info = (
        torch.cuda.get_device_properties(0).name if torch.cuda.is_available() else "cpu"
    )

    # A1-002: log git hash, hardware, dataset info alongside hyperparams
    wandb.init(
        project=settings.wandb_project,
        entity=settings.wandb_entity or None,
        config={
            **TRAIN_CONFIG,
            "git_commit": _git_hash,
            "python_version": platform.python_version(),
            "cuda_version": torch.version.cuda,
            "gpu": _gpu_info,
        },
        name="qlora-r32-codellama-7b",
    )

    # Load model with Unsloth (4-bit quantized for training)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=TRAIN_CONFIG["base_model"],
        max_seq_length=TRAIN_CONFIG["max_seq_length"],
        load_in_4bit=True,
        dtype=None,
    )

    # Apply LoRA
    model = FastLanguageModel.get_peft_model(
        model,
        r=TRAIN_CONFIG["lora_r"],
        lora_alpha=TRAIN_CONFIG["lora_alpha"],
        lora_dropout=TRAIN_CONFIG["lora_dropout"],
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    # Load, validate, and redact data
    dataset, eval_dataset, cache_hash = load_training_data()
    wandb.config.update({
        "dataset_fingerprint": dataset._fingerprint,
        "eval_fingerprint": eval_dataset._fingerprint,
        "dataset_cache_hash": cache_hash,
        "dataset_size": len(dataset),
        "eval_size": len(eval_dataset),
    })
    logger.info("training_start", dataset_size=len(dataset), eval_size=len(eval_dataset))

    # A1-005: eval_strategy added
    training_args = SFTConfig(
        output_dir="./outputs/qlora-r32",
        per_device_train_batch_size=TRAIN_CONFIG["per_device_train_batch_size"],
        gradient_accumulation_steps=TRAIN_CONFIG["gradient_accumulation_steps"],
        num_train_epochs=TRAIN_CONFIG["num_train_epochs"],
        learning_rate=TRAIN_CONFIG["learning_rate"],
        warmup_ratio=TRAIN_CONFIG["warmup_ratio"],
        lr_scheduler_type=TRAIN_CONFIG["lr_scheduler_type"],
        weight_decay=TRAIN_CONFIG["weight_decay"],
        bf16=TRAIN_CONFIG["bf16"],
        logging_steps=10,
        save_steps=500,
        save_total_limit=3,
        seed=TRAIN_CONFIG["seed"],
        report_to="wandb",
        max_seq_length=TRAIN_CONFIG["max_seq_length"],
        dataset_text_field="text",
        eval_strategy="steps",
        eval_steps=500,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        eval_dataset=eval_dataset,
        args=training_args,
    )

    trainer.train()

    # Save adapter and reproducibility config
    output_path = Path("./outputs/qlora-r32/final")
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)

    final_loss = trainer.state.log_history[-1].get("loss", 0)
    wandb.log({"final_train_loss": final_loss})
    wandb.finish()

    (output_path / "train_config.json").write_text(json.dumps(TRAIN_CONFIG, indent=2))
    logger.info("model_saved", output_path=str(output_path), final_train_loss=final_loss)


if __name__ == "__main__":
    train()
