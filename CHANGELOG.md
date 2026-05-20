# Changelog

## [0.3.1] - 2026-05-19
### Fixed
- Cache compiled graph as singleton (avoid rebuild per request)
- Document LangGraph fan-in behavior for skipped agents

## [0.3.0] - 2026-05-12
### Added
- AWQ/GPTQ/GGUF quantization comparison pipeline
- HuggingFace Hub publishing script
- W&B sweep config for hyperparameter search

## [0.2.0] - 2026-05-01
### Added
- LangGraph state machine with conditional routing
- Security, style, and complexity agent nodes
- Summarizer with prioritized output
- FastAPI serving endpoint

## [0.1.0] - 2026-04-20
### Added
- QLoRA training script (Unsloth + TRL)
- Dataset preparation and filtering
- W&B experiment tracking integration
