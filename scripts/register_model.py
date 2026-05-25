"""Record model version, lineage, and hash in the JSON model registry.

Fix A3-ABSENT (model registry): records training data version, code commit,
model hash, and eval loss per model version. Replace the JSON file backend
with MLflow Model Registry or W&B Artifacts in production — the schema is
identical.

Usage:
    python scripts/register_model.py \
        ./outputs/qlora-r32/final \
        <dataset_fingerprint> \
        <eval_loss>

Rollback procedure (target: ≤5 minutes):
    1. Identify target version from outputs/model_registry.json
    2. kubectl set image deployment/coderev-agents \
           coderev-agents=ghcr.io/poojakira/coderev-agents:<target-version>
    3. kubectl rollout status deployment/coderev-agents --timeout=120s
    4. curl -H "X-API-Key: $CODEREV_API_SECRET_KEY" https://<host>/health
    Total: <2 min warm node, <5 min cold pull.
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def compute_dir_hash(model_dir: str) -> str:
    """SHA-256 over all model files, sorted by relative path."""
    p = Path(model_dir)
    h = hashlib.sha256()
    for f in sorted(p.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(p).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def register(
    model_dir: str,
    dataset_fingerprint: str,
    eval_loss: float,
    registry_path: str = "./outputs/model_registry.json",
) -> dict:
    git_hash = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    model_hash = compute_dir_hash(model_dir)
    entry = {
        "model_hash": model_hash,
        "model_dir": model_dir,
        "git_commit": git_hash,
        "dataset_fingerprint": dataset_fingerprint,
        "eval_loss": eval_loss,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "version": f"sha256:{model_hash[:12]}",
    }
    reg_path = Path(registry_path)
    registry: list[dict] = json.loads(reg_path.read_text()) if reg_path.exists() else []
    registry.append(entry)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(registry, indent=2))
    print(f"Registered model version sha256:{model_hash[:12]}")
    return entry


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(
            "Usage: python scripts/register_model.py <model_dir> <dataset_fingerprint> <eval_loss>"
        )
    register(
        model_dir=sys.argv[1],
        dataset_fingerprint=sys.argv[2],
        eval_loss=float(sys.argv[3]),
    )
