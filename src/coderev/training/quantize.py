"""Quantization pipeline — AWQ, GPTQ, GGUF comparison."""

import json
import time
from pathlib import Path

import torch
from transformers import AutoTokenizer


def quantize_awq(model_path: str, output_dir: str) -> dict:
    """Quantize model using AWQ 4-bit."""
    from awq import AutoAWQForCausalLM

    start = time.time()
    model = AutoAWQForCausalLM.from_pretrained(model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    quant_config = {"zero_point": True, "q_group_size": 128, "w_bit": 4, "version": "GEMM"}
    model.quantize(tokenizer, quant_config=quant_config)

    out = Path(output_dir) / "awq"
    out.mkdir(parents=True, exist_ok=True)
    model.save_quantized(str(out))
    tokenizer.save_pretrained(str(out))

    elapsed = time.time() - start
    size_mb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1024 / 1024
    return {"method": "AWQ-4bit", "time_s": round(elapsed, 1), "size_mb": round(size_mb, 1)}


def quantize_gptq(model_path: str, output_dir: str) -> dict:
    """Quantize model using GPTQ 4-bit."""
    from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

    start = time.time()
    quantize_config = BaseQuantizeConfig(bits=4, group_size=128, damp_percent=0.1)

    model = AutoGPTQForCausalLM.from_pretrained(model_path, quantize_config)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    # Calibration data
    examples = [tokenizer("def hello():\n    return 'world'", return_tensors="pt")]
    model.quantize(examples)

    out = Path(output_dir) / "gptq"
    out.mkdir(parents=True, exist_ok=True)
    model.save_quantized(str(out))
    tokenizer.save_pretrained(str(out))

    elapsed = time.time() - start
    size_mb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1024 / 1024
    return {"method": "GPTQ-4bit", "time_s": round(elapsed, 1), "size_mb": round(size_mb, 1)}


def quantize_gguf(model_path: str, output_dir: str) -> dict:
    """Convert model to GGUF Q4_K_M format."""
    import subprocess

    start = time.time()
    out = Path(output_dir) / "gguf"
    out.mkdir(parents=True, exist_ok=True)
    output_file = out / "model-q4_k_m.gguf"

    # Uses llama.cpp convert script
    subprocess.run(
        ["python", "-m", "llama_cpp.convert", model_path, "--outfile", str(output_file),
         "--outtype", "q4_k_m"],
        check=True,
    )

    elapsed = time.time() - start
    size_mb = output_file.stat().st_size / 1024 / 1024 if output_file.exists() else 0
    return {"method": "GGUF-Q4_K_M", "time_s": round(elapsed, 1), "size_mb": round(size_mb, 1)}


def benchmark_inference(model_path: str, method: str) -> dict:
    """Benchmark inference speed for a quantized model."""
    from transformers import AutoModelForCausalLM

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(model_path, device_map="auto")

    prompt = "Review this code:\n```python\ndef login(user, pwd):\n    if pwd == 'admin':\n        return True\n```\n"
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    # Warmup
    with torch.no_grad():
        model.generate(**inputs, max_new_tokens=10)

    # Benchmark
    start = time.time()
    num_runs = 5
    total_tokens = 0
    for _ in range(num_runs):
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=128)
            total_tokens += out.shape[1] - inputs["input_ids"].shape[1]

    elapsed = time.time() - start
    tok_per_sec = total_tokens / elapsed

    return {"method": method, "tokens_per_sec": round(tok_per_sec, 1), "runs": num_runs}


def run_comparison(merged_model_path: str, output_dir: str = "./outputs/quantized"):
    """Run full quantization comparison."""
    results = []

    print("=== AWQ Quantization ===")
    results.append(quantize_awq(merged_model_path, output_dir))

    print("=== GPTQ Quantization ===")
    results.append(quantize_gptq(merged_model_path, output_dir))

    print("=== GGUF Conversion ===")
    results.append(quantize_gguf(merged_model_path, output_dir))

    # Save comparison
    out_path = Path(output_dir) / "comparison.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out_path}")
    print("\n| Method | Size (MB) | Time (s) |")
    print("|--------|-----------|----------|")
    for r in results:
        print(f"| {r['method']} | {r['size_mb']} | {r['time_s']} |")

    return results


if __name__ == "__main__":
    import sys
    model_path = sys.argv[1] if len(sys.argv) > 1 else "./outputs/qlora-r32/merged"
    run_comparison(model_path)
