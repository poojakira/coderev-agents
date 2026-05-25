"""Post-hoc output validation for raw LLM string responses.

Used as a fallback when structured output is unavailable (e.g. local model
that does not support function-calling). For OpenAI-backed nodes, prefer
with_structured_output() in output_schemas.py (GAP-A6-001).

Finding A2-007: raw LLM strings written directly to ReviewState with no
length cap or control-character stripping.
"""
import re

from pydantic import BaseModel, Field, field_validator

# UNVERIFIED: 8000 chars — set based on observed p99 response length from
# a production run. Replace with measured value once traffic data is available.
_MAX_REVIEW_LEN = 8000


class ReviewOutput(BaseModel):
    content: str = Field(..., min_length=1, max_length=_MAX_REVIEW_LEN)

    @field_validator("content")
    @classmethod
    def strip_control_chars(cls, v: str) -> str:
        # Remove ASCII control characters except tab (0x09) and newline (0x0a)
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v)


def validate_agent_output(raw: str) -> str:
    """Validate and sanitize raw LLM output before writing to ReviewState.

    Raises pydantic.ValidationError if content is empty or exceeds max length.
    Strips ASCII control characters that have no place in a review text.
    """
    return ReviewOutput(content=raw).content
