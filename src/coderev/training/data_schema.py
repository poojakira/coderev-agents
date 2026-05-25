"""Pandera schema contract for the code review training dataset.

Fix A4-001: schema validated at load time before any processing.
Violations raise pa.errors.SchemaErrors and abort the run — silent skips
allow poisoned rows to accumulate undetected.
"""
import pandera as pa
from pandera.typing import Series


class CodeReviewSchema(pa.DataFrameModel):
    """Enforced on every training and evaluation row before formatting.

    Column presence, types, and value constraints checked at load time.
    """

    diff: Series[str] = pa.Field(
        str_length={"min_value": 50, "max_value": 200_000},
        nullable=False,
        description="Raw unified diff string",
    )
    review: Series[str] = pa.Field(
        str_length={"min_value": 20, "max_value": 50_000},
        nullable=False,
        description="Human-written review text",
    )

    class Config:
        coerce = False      # never silently cast — fail on wrong type
        strict = "filter"   # drop unknown columns, keep schema columns only
