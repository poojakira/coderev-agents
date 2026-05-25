"""Configuration for coderev-agents.

All secret fields use pydantic SecretStr to prevent accidental logging.
Access secret values only via .get_secret_value() at the call site.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM — secret; never log the raw value
    llm_model: str = "gpt-4o-mini"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""
    llm_temperature: float = 0.2

    # Fine-tuned model (for local serving)
    local_model_path: str = ""
    use_local_model: bool = False

    # Agent config
    max_diff_lines: int = 500
    security_scan_threshold: int = 10  # skip security for diffs < N lines
    timeout_seconds: int = 30

    # API authentication — secret; never log the raw value
    api_secret_key: SecretStr = SecretStr("")

    # W&B
    wandb_project: str = "coderev-agents"
    wandb_entity: str = ""

    # HuggingFace — secret
    hf_repo_id: str = "poojakira/coderev-codellama-7b-lora"
    hf_token: SecretStr = SecretStr("")

    # Environment: "dev" or "production"
    env: str = "dev"
    # Comma-separated allowed hosts for TLS redirect in production
    allowed_hosts: str = "localhost"

    model_config = {"env_prefix": "CODEREV_", "env_file": ".env"}
