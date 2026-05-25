"""Quantization pipeline — AWQ, GPTQ, GGUF comparison.

Fixes applied:
  A1-004 — benchmark_inference uses format-appropriate loader for AWQ/GPTQ/GGUF
  A5-002 — path traversal fix: model_path and output_dir resolved and validated
  A1-003 — print() replaced with structlog
"""

import json
import time
from pathlib import Path

import structlog
import torch
from transformers import AutoTokenizer

logger = structlog.get_logger()


def _resolve_paths(model_path: str, output_dir: str) -> tuple[Path, Path]:
    """Resolve and validate both paths. Raises ValueError on traversal attempt.

    Fix A5-002 / CWE-78: rejects output_dir outside workspace root.
    model_path may be an external cache directory — not constrained.
    """
    resolved_model = Path(model_path).resolve()
    resolved_output = Path(output_dir).resolve()
    workspace_root = Path("./outputs").resolve()

    if not resolved_model.exists():
        raise ValueError(f"model_path does not exist: {resolved_model}")
    if not str(resolved_output).startswith(str(workspace_root)):
        raise ValueError(
            f"output_dir {resolved_output} is outside workspace root {workspace_root}"
        )
    return resolved_model, resolved_output


def quantize_awq(model_path: str, output_dir: str) -> dict:
    """Quantize model using AWQ 4-bit."""
    from awq import AutoAWQForCausalLM

    resolved_model, resolved_output = _resolve_paths(model_path, output_dir)
    start = time.time()
    model = AutoAWQForCausalLM.from_pretrained(str(resolved_model))
    tokenizer = AutoTokenizer.from_pretrained(str(resolved_model))

    quant_config = {"zero_point": True, "q_group_size": 128, "w_bit": 4, "version": "GEMM"}
    model.quantize(tokenizer, quant_config=quant_config)

    out = resolved_output / "awq"
    out.mkdir(parents=True, exist_ok=True)
    model.save_quantized(str(out))
    tokenizer.save_pretrained(str(out))

    elapsed = time.time() - start
    size_mb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1024 / 1024
    result = {"method": "AWQ-4bit", "time_s": round(elapsed, 1), "size_mb": round(size_mb, 1)}
    logger.info("quantize_awq_complete", **result)
    return result


def quantize_gptq(model_path: str, output_dir: str) -> dict:
    """Quantize model using GPTQ 4-bit."""
    from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

    resolved_model, resolved_output = _resolve_paths(model_path, output_dir)
    start = time.time()
    quantize_config = BaseQuantizeConfig(bits=4, group_size=128, damp_percent=0.1)

    model = AutoGPTQForCausalLM.from_pretrained(str(resolved_model), quantize_config)
    tokenizer = AutoTokenizer.from_pretrained(str(resolved_model))

    examples = [tokenizer("def hello():\n    return 'world'", return_tensors="pt")]
    model.quantize(examples)

    out = resolved_output / "gptq"
    out.mkdir(parents=True, exist_ok=True)
    model.save_quantized(str(out))
    tokenizer.save_pretrained(str(out))

    elapsed = time.time() - start
    size_mb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1024 / 1024
    result = {"method": "GPTQ-4bit", "time_s": round(elapsed, 1), "size_mb": round(size_mb, 1)}
    logger.info("quantize_gptq_complete", **result)
    return result


def quantize_gguf(model_path: str, output_dir: str) -> dict:
    """Convert model to GGUF Q4_K_M format.

    Fix A5-002: paths resolved and validated before subprocess call.
    subprocess.run uses shell=False (explicit) with a timeout.
    """
    import subprocess

    resolved_model, resolved_output = _resolve_paths(model_path, output_dir)
    start = time.time()
    out = resolved_output / "gguf"
    out.mkdir(parents=True, exist_ok=True)
    output_file = out / "model-q4_k_m.gguf"

    subprocess.run(
        [
            "python", "-m", "llama_cpp.convert",
            str(resolved_model),          # resolved path — no shell expansion
            "--outfile", str(output_file),
            "--outtype", "q4_k_m",
        ],
        check=True,
        shell=False,                     # explicit — never shell=True
        timeout=3600,                    # prevent indefinite hang
    )

    elapsed = time.time() - start
    size_mb = output_file.stat().st_size / 1024 / 1024 if output_file.exists() else 0
    result = {"method": "GGUF-Q4_K_M", "time_s": round(elapsed, 1), "size_mb": round(size_mb, 1)}
    logger.info("quantize_gguf_complete", **result)
    return result


def benchmark_inference(model_path: str, method: str) -> dict:
    """Benchmark inference speed using the format-appropriate model loader.

    Fix A1-004: each quantization format uses its own loader, not a generic
    AutoModelForCausalLM which silently ignores quantization.
    """
    prompt = (
        "Review this code:\n```python\ndef login(user, pwd):\n"
        "    if pwd == 'admin':\n        return True\n```\n"
    )

    if method.startswith("AWQ"):
        from awq import AutoAWQForCausalLM
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoAWQForCausalLM.from_quantized(
            model_path, fuse_layers=True, device_map="auto"
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(
            next(model.parameters()).device
        )
        with torch.no_grad():
            model.generate(**inputs, max_new_tokens=10)  # warmup
        start = time.time()
        num_runs, total_tokens = 5, 0
        for _ in range(num_runs):
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=128)
                total_tokens += out.shape[1] - inputs["input_ids"].shape[1]

    elif method.startswith("GPTQ"):
        from auto_gptq import AutoGPTQForCausalLM
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoGPTQForCausalLM.from_quantized(
            model_path, device="cuda:0", use_triton=True
        )
        inputs = tokenizer(prompt, return_tensors="pt").to("cuda:0")
        with torch.no_grad():
            model.generate(**inputs, max_new_tokens=10)
        start = time.time()
        num_runs, total_tokens = 5, 0
        for _ in range(num_runs):
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=128)
                total_tokens += out.shape[1] - inputs["input_ids"].shape[1]

    else:  # GGUF — uses llama-cpp-python API
        from llama_cpp import Llama
        gguf_file = next(Path(model_path).glob("*.gguf"))
        model = Llama(model_path=str(gguf_file), n_gpu_layers=-1, verbose=False)
        model(prompt, max_tokens=10)  # warmup
        start = time.time()
        num_runs, total_tokens = 5, 0
        for _ in range(num_runs):
            out = model(prompt, max_tokens=128)
            total_tokens += out["usage"]["completion_tokens"]

    elapsed = time.time() - start
    result = {
        "method": method,
        "tokens_per_sec": round(total_tokens / elapsed, 1),
        "runs": num_runs,
    }
    logger.info("benchmark_complete", **result)
    return result


def run_comparison(merged_model_path: str, output_dir: str = "./outputs/quantized"):
    """Run full quantization comparison."""
    results = []

    logger.info("quantize_start", method="AWQ")
    results.append(quantize_awq(merged_model_path, output_dir))

    logger.info("quantize_start", method="GPTQ")
    results.append(quantize_gptq(merged_model_path, output_dir))

    logger.info("quantize_start", method="GGUF")
    results.append(quantize_gguf(merged_model_path, output_dir))

    out_path = Path(output_dir) / "comparison.json"
    out_path.write_text(json.dumps(results, indent=2))
    logger.info("comparison_saved", path=str(out_path))

    logger.info(
        "comparison_table",
        rows=[
            {"method": r["method"], "size_mb": r["size_mb"], "time_s": r["time_s"]}
            for r in results
        ],
    )
    return results


if __name__ == "__main__":
    import sys

    model_path = sys.argv[1] if len(sys.argv) > 1 else "./outputs/qlora-r32/merged"
    run_comparison(model_path)
