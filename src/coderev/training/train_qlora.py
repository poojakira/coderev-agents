"""QLoRA fine-tuning of CodeLlama-7B on code review data using Unsloth + TRL."""

import json
from pathlib import Path

import wandb
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig
from unsloth import FastLanguageModel

from coderev.config import Settings

settings = Settings()

# Training hyperparameters
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
}


def format_review_example(example: dict) -> str:
    """Format a code review example into instruction format."""
    return (
        f"### Instruction:\nReview this code change for bugs, security issues, and style.\n\n"
        f"### Input:\n```\n{example['diff']}\n```\n\n"
        f"### Response:\n{example['review']}"
    )


def load_training_data(dataset_name: str = "JetBrains/code-review"):
    """Load and format code review dataset."""
    # Security (B615): In production, pin dataset revision with revision= parameter
    # to prevent supply-chain attacks via mutable HuggingFace Hub dataset tags.
    ds = load_dataset(dataset_name, split="train")  # noqa: S615
    ds = ds.filter(lambda x: len(x.get("diff", "")) > 50 and len(x.get("review", "")) > 20)
    ds = ds.map(lambda x: {"text": format_review_example(x)})
    return ds


def train():
    """Run QLoRA fine-tuning with W&B tracking."""
    # Initialize W&B
    wandb.init(
        project=settings.wandb_project,
        entity=settings.wandb_entity or None,
        config=TRAIN_CONFIG,
        name="qlora-r32-codellama-7b",
    )

    # Load model with Unsloth (4-bit quantized for training)
    # Security (B615): In production, add revision= with a pinned commit SHA to
    # prevent model substitution attacks via mutable HuggingFace Hub model tags.
    model, tokenizer = FastLanguageModel.from_pretrained(  # noqa: S615
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
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    # Load data
    dataset = load_training_data()
    import logging; logging.info(f"Training on {len(dataset)} examples")

    # Training config
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
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
    )

    # Train
    trainer.train()

    # Save adapter
    output_path = Path("./outputs/qlora-r32/final")
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)

    # Log final metrics
    wandb.log({"final_train_loss": trainer.state.log_history[-1].get("loss", 0)})
    wandb.finish()

    # Save config for reproducibility
    (output_path / "train_config.json").write_text(json.dumps(TRAIN_CONFIG, indent=2))
    import logging; logging.info(f"Model saved to {output_path}")


if __name__ == "__main__":
    train()
