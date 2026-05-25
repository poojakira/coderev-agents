"""Generate SHA-256 manifest for a model directory.

Run this script after training or downloading a model to produce
model_manifest.json. The manifest is consumed by model_loader.verify_model_manifest()
before any model is loaded in production. Fix A2-005 / CWE-345.

Usage:
    python scripts/generate_model_manifest.py ./outputs/qlora-r32/final

The manifest records the SHA-256 of every file in the directory (excluding
model_manifest.json itself). Store it alongside the model artifacts and
optionally sign it with GPG or Sigstore for full supply-chain provenance.
"""
import hashlib
import json
import sys
from pathlib import Path


def generate(model_dir: str) -> None:
    p = Path(model_dir)
    if not p.exists():
        raise SystemExit(f"Directory does not exist: {model_dir}")

    manifest: dict[str, str] = {}
    for f in sorted(p.rglob("*")):
        if f.is_file() and f.name != "model_manifest.json":
            rel = f.relative_to(p).as_posix()
            manifest[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
            print(f"  hashed: {rel}")

    out = p / "model_manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written: {out} ({len(manifest)} files)")
    print(
        "Next step: sign this manifest with 'gpg --detach-sign model_manifest.json' "
        "or via Sigstore cosign for full provenance."
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/generate_model_manifest.py <model_dir>")
    generate(sys.argv[1])
