"""Model weight integrity verification before loading.

Fix A2-005 / CWE-345: verify SHA-256 manifest before any model is loaded
from local_model_path. A backdoored or tampered model file raises RuntimeError
before it can be instantiated.

Usage:
    verify_model_manifest("/path/to/model_dir")
    # then load the model normally

Generate the manifest after training:
    python scripts/generate_model_manifest.py /path/to/model_dir
"""

import hashlib
import hmac
import json
from pathlib import Path

import structlog

logger = structlog.get_logger()


def verify_model_manifest(model_dir: str) -> None:
    """Verify all model files match the SHA-256 hashes in model_manifest.json.

    Raises RuntimeError if:
    - model_manifest.json does not exist in model_dir
    - any listed file is missing from model_dir
    - any file's SHA-256 does not match the recorded hash

    The manifest itself must be protected externally (GPG or Sigstore signature)
    before full supply-chain trust is granted. This function enforces file
    integrity only — it does not verify the manifest's own provenance.
    """
    manifest_path = Path(model_dir) / "model_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(
            f"model_manifest.json not found in {model_dir}. "
            "Run scripts/generate_model_manifest.py after training to create it."
        )

    manifest: dict[str, str] = json.loads(manifest_path.read_text())

    for filename, expected_hex in manifest.items():
        file_path = Path(model_dir) / filename
        if not file_path.exists():
            raise RuntimeError(f"Model file missing: {file_path}")
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if not hmac.compare_digest(actual, expected_hex):
            raise RuntimeError(
                f"Hash mismatch for {filename}: "
                f"expected {expected_hex[:16]}… got {actual[:16]}…"
            )
        logger.info("model_file_verified", file=filename)

    logger.info(
        "model_manifest_verified",
        model_dir=str(model_dir),
        files_checked=len(manifest),
    )
