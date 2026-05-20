"""Publish fine-tuned model and adapter to HuggingFace Hub."""

from pathlib import Path

from huggingface_hub import HfApi, create_repo

from coderev.config import Settings


def publish_adapter(adapter_path: str = "./outputs/qlora-r32/final"):
    """Push LoRA adapter to HuggingFace Hub."""
    settings = Settings()
    api = HfApi(token=settings.hf_token)

    repo_id = settings.hf_repo_id
    create_repo(repo_id, exist_ok=True, token=settings.hf_token)

    api.upload_folder(
        folder_path=adapter_path,
        repo_id=repo_id,
        commit_message="Upload QLoRA adapter (r=32, alpha=64)",
    )
    print(f"Adapter published to https://huggingface.co/{repo_id}")


def publish_quantized(model_path: str = "./outputs/quantized/awq"):
    """Push quantized model to HuggingFace Hub."""
    settings = Settings()
    api = HfApi(token=settings.hf_token)

    repo_id = f"{settings.hf_repo_id.rsplit('-', 1)[0]}-awq"
    create_repo(repo_id, exist_ok=True, token=settings.hf_token)

    api.upload_folder(
        folder_path=model_path,
        repo_id=repo_id,
        commit_message="Upload AWQ 4-bit quantized model",
    )
    print(f"Quantized model published to https://huggingface.co/{repo_id}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--quantized":
        publish_quantized()
    else:
        publish_adapter()
