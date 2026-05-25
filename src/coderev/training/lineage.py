"""Queryable transformation lineage recorder.

Fix ABSENT-A4: records every transformation step — what went in, what came
out, which function ran, at what timestamp, with what parameters.

Writes JSON-Lines to ./outputs/lineage.jsonl.
In production, replace the file backend with MLflow run tags or W&B Artifacts.
The schema is identical — only the sink changes.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()
_LINEAGE_PATH = Path("./outputs/lineage.jsonl")


def record_transform(
    step_name: str,
    input_fingerprint: str,
    output_fingerprint: str,
    parameters: dict[str, Any],
    row_count_in: int,
    row_count_out: int,
) -> None:
    """Append one transformation record to the lineage log.

    Args:
        step_name: e.g. "pii_redaction", "train_test_split", "schema_validation"
        input_fingerprint: HF dataset ._fingerprint or SHA-256 of input artifact
        output_fingerprint: HF dataset ._fingerprint or SHA-256 of output artifact
        parameters: all parameters that determined the transformation outcome
        row_count_in: rows entering this step
        row_count_out: rows exiting this step (may differ after filtering)
    """
    event = {
        "step": step_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_fingerprint": input_fingerprint,
        "output_fingerprint": output_fingerprint,
        "parameters": parameters,
        "row_count_in": row_count_in,
        "row_count_out": row_count_out,
        "params_hash": hashlib.sha256(
            json.dumps(parameters, sort_keys=True).encode()
        ).hexdigest()[:12],
    }
    _LINEAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LINEAGE_PATH.open("a") as fh:
        fh.write(json.dumps(event) + "\n")
    logger.info(
        "lineage_recorded",
        step=step_name,
        rows_in=row_count_in,
        rows_out=row_count_out,
    )


def query_lineage(step_name: str | None = None) -> list[dict]:
    """Return all lineage records, optionally filtered by step name.

    Args:
        step_name: if provided, return only records for this step

    Returns:
        list of lineage event dicts in chronological order
    """
    if not _LINEAGE_PATH.exists():
        return []
    records = [
        json.loads(line)
        for line in _LINEAGE_PATH.read_text().splitlines()
        if line.strip()
    ]
    if step_name:
        records = [r for r in records if r["step"] == step_name]
    return records
