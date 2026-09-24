"""Observed outcomes recorded against decisions.

Outcomes close the feedback loop. Once recorded, a decision's predicted
distribution and selected action can be scored against what actually happened,
which is what calibration (Brier score, ECE) consumes.

DecisionOS never retrains a model in v1; outcomes are stored so the data
infrastructure for future evaluation is in place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Outcome(BaseModel):
    """The observed result of acting on a decision.

    Attributes
    ----------
    decision_id:
        The decision this outcome belongs to.
    actual_outcome:
        Domain-specific label for what happened, e.g. ``"safe"``. Kept as a
        string because the meaningful vocabulary is schema-defined.
    success:
        Whether the action was correct / produced the desired result. This is
        the ground truth used for calibration.
    metadata:
        Optional extra details (measurements, notes, source system).
    recorded_at:
        When the outcome was recorded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str = Field(min_length=1)
    actual_outcome: str = Field(min_length=1, max_length=255)
    success: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("actual_outcome")
    @classmethod
    def _validate_actual_outcome(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("actual_outcome must not be blank")
        return value


__all__ = ["Outcome"]
