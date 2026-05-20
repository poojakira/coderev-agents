# CodeRev Agents — Multi-Agent Code Review with Fine-tuned LLM

[![CI](https://github.com/poojakira/coderev-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/poojakira/coderev-agents/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![W&B](https://img.shields.io/badge/W%26B-Experiments-yellow)](https://wandb.ai/poojakira/coderev-agents)

Multi-agent code review system powered by a fine-tuned CodeLlama-7B and LangGraph orchestration. Specialized agents analyze security, style, and complexity in parallel.

**[HuggingFace Model](https://huggingface.co/poojakira/coderev-codellama-7b-lora)** · **[Live Demo](https://huggingface.co/spaces/poojakira/coderev-demo)** · **[W&B Experiments](https://wandb.ai/poojakira/coderev-agents)**

---

## Architecture

```
                    ┌─────────────────┐
                    │  Orchestrator   │
                    │ (route by diff) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───┐  ┌──────▼─────┐  ┌────▼────────┐
     │  Security  │  │   Style    │  │ Complexity  │
     │   Agent    │  │   Agent    │  │   Agent     │
     └────────┬───┘  └──────┬─────┘  └────┬────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │   Summarizer    │
                    │ (prioritized)   │
                    └─────────────────┘
```

**Conditional routing:** Orchestrator skips security scan for trivial diffs (<10 lines) and complexity analysis for short changes (<20 lines). Style always runs.

## Model Performance

| Metric | Base CodeLlama-7B | Fine-tuned (QLoRA r=32) | AWQ-4bit |
|--------|-------------------|-------------------------|----------|
| Review Quality (LLM-judge, 1-5) | 2.8 | 4.2 | 4.1 |
| Security Issue Detection (F1) | 0.41 | 0.73 | 0.71 |
| Perplexity (test set) | 8.4 | 5.1 | 5.3 |
| Inference Speed (tok/s, A10G) | 45 | 45 | 112 |
| VRAM Usage | 14GB | 14GB | 4.2GB |

## Quantization Comparison

| Method | Size | Quantize Time | Perplexity | Tokens/sec |
|--------|------|---------------|------------|------------|
| FP16 (baseline) | 13.5 GB | — | 5.1 | 45 |
| AWQ 4-bit | 4.1 GB | 8 min | 5.3 | 112 |
| GPTQ 4-bit | 4.0 GB | 25 min | 5.4 | 98 |
| GGUF Q4_K_M | 4.3 GB | 3 min | 5.5 | 85 |

## Quick Start

```bash
git clone https://github.com/poojakira/coderev-agents.git
cd coderev-agents
pip install -e .

# Set API key (uses OpenAI-compatible API for agents)
export CODEREV_LLM_API_KEY=sk-your-key

# Run API
uvicorn coderev.api.main:app --reload

# Submit a review
curl -X POST http://localhost:8000/v1/review \
  -H "Content-Type: application/json" \
  -d '{"diff": "- password = input()\n+ password = hashlib.sha256(input().encode()).hexdigest()"}'
```

## Training

```bash
# Install training dependencies
pip install -e ".[train]"

# Fine-tune (requires GPU — A100 recommended)
python -m coderev.training.train_qlora

# Quantize
pip install -e ".[quantize]"
python -m coderev.training.quantize ./outputs/qlora-r32/merged

# Publish to HuggingFace
python scripts/publish_hf.py
```

## Project Structure

```
coderev-agents/
├── src/coderev/
│   ├── agents/
│   │   ├── graph.py          # LangGraph StateGraph with conditional routing
│   │   └── nodes.py          # Agent implementations (security, style, complexity)
│   ├── training/
│   │   ├── train_qlora.py    # Unsloth + TRL fine-tuning with W&B
│   │   └── quantize.py       # AWQ/GPTQ/GGUF comparison pipeline
│   ├── api/
│   │   └── main.py           # FastAPI serving endpoint
│   └── config.py             # Pydantic settings
├── configs/
│   ├── train_qlora.yaml      # Training hyperparameters
│   └── sweep.yaml            # W&B hyperparameter sweep
├── scripts/
│   └── publish_hf.py         # HuggingFace Hub publishing
└── tests/
    └── test_graph.py         # Routing and orchestration tests
```

## Training Details

- **Base model:** CodeLlama-7B-Instruct
- **Method:** QLoRA (r=32, α=64, dropout=0.05)
- **Dataset:** JetBrains/code-review (87K examples after filtering)
- **Hardware:** 1x A100-40GB, 4.2 hours
- **Optimizer:** AdamW, cosine LR schedule
- **Final train loss:** 0.847

## License

MIT
