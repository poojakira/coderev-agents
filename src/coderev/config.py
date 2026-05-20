"""Configuration for coderev-agents."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_temperature: float = 0.2

    # Fine-tuned model (for local serving)
    local_model_path: str = ""
    use_local_model: bool = False

    # Agent config
    max_diff_lines: int = 500
    security_scan_threshold: int = 10  # skip security for diffs < N lines
    timeout_seconds: int = 30

    # W&B
    wandb_project: str = "coderev-agents"
    wandb_entity: str = ""

    # HuggingFace
    hf_repo_id: str = "poojakira/coderev-codellama-7b-lora"
    hf_token: str = ""

    model_config = {"env_prefix": "CODEREV_", "env_file": ".env"}
