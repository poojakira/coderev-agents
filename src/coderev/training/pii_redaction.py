"""PII detection and redaction for training data.

Fix A4-003 / CWE-359: screens training data before model ingestion.
Fine-tuned LLMs memorize training data and can reproduce it verbatim at
inference. Reference: Carlini et al., "Extracting Training Data from Large
Language Models", USENIX Security 2021, arXiv:2012.07805.

Covers the most common PII types found in real code review datasets.
Extend _PII_PATTERNS for domain-specific identifiers.
"""
import re

import structlog

logger = structlog.get_logger()

# Regex-based PII patterns.
# Never log the matched values — log only type and count.
_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    (
        "PHONE",
        re.compile(r"\b(\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b"),
    ),
    (
        "IPV4",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
    ),
    (
        "API_KEY",
        re.compile(r"\b(?:sk|pk|api|token|key)[-_][A-Za-z0-9]{20,}\b", re.I),
    ),
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "JWT",
        re.compile(
            r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"
        ),
    ),
    ("GITHUB_PAT", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("HF_TOKEN", re.compile(r"\bhf_[A-Za-z0-9]{34}\b")),
]


def redact_pii(text: str, row_id: int = -1) -> tuple[str, list[str]]:
    """Replace PII matches with [REDACTED:<TYPE>] tokens.

    Args:
        text: input string to scan
        row_id: dataset row index for log correlation (not logged as PII)

    Returns:
        redacted_text: text with PII replaced by typed placeholder tokens
        findings: list of PII type labels found (NOT the matched values)
    """
    findings: list[str] = []
    for label, pattern in _PII_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            findings.append(f"{label}:{len(matches)}")
            text = pattern.sub(f"[REDACTED:{label}]", text)
    return text, findings


def redact_dataset_row(example: dict, idx: int = 0) -> dict:
    """HuggingFace datasets.map() compatible row-level redaction function."""
    diff_clean, diff_findings = redact_pii(example.get("diff", ""), row_id=idx)
    review_clean, review_findings = redact_pii(example.get("review", ""), row_id=idx)
    all_findings = diff_findings + review_findings

    if all_findings:
        logger.warning(
            "pii_redacted",
            row_id=idx,
            findings=all_findings,
            # Intentionally NOT logging matched text — only type:count pairs
        )

    return {
        **example,
        "diff": diff_clean,
        "review": review_clean,
        "_pii_findings": ",".join(all_findings),
    }
