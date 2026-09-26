"""Typed SDK result objects.

These mirror the API responses but are intentionally lenient (extra fields are
allowed) so a newer server can add fields without breaking an older client.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicySummary(BaseModel):
    """Policy outcome attached to a decision."""

    model_config = ConfigDict(extra="allow")

    name: str
    version: int
    precedence: str
    overridden: bool
    triggered_rules: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """A decision returned by the API."""

    model_config = ConfigDict(extra="allow")

    decision_id: str
    decision_type: str
    schema_name: str
    schema_version: int
    action: str
    model_action: str
    confidence: float
    probabilities: dict[str, float]
    risk: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    provider: str
    provider_request_id: str | None = None
    latency_ms: float
    state: str | None = None
    policy: PolicySummary | None = None
    created_at: datetime

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"Decision({self.decision_id}, action={self.action!r})"


class Outcome(BaseModel):
    """An observed outcome recorded for a decision."""

    model_config = ConfigDict(extra="allow")

    decision_id: str
    actual_outcome: str
    success: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime


class DecisionEvent(BaseModel):
    """One entry in a decision's audit trail."""

    model_config = ConfigDict(extra="allow")

    type: str
    from_state: str | None = None
    to_state: str | None = None
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class Explanation(BaseModel):
    """Structured evidence for a decision."""

    model_config = ConfigDict(extra="allow")

    decision_id: str
    decision: str
    model_action: str
    model_probabilities: dict[str, float]
    confidence: float
    risk: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    policy_rules_triggered: list[str] = Field(default_factory=list)
    policy_precedence: str | None = None
    provider: str
    schema_name: str
    schema_version: int
    lifecycle: list[DecisionEvent] = Field(default_factory=list)


class Schema(BaseModel):
    """A decision schema."""

    model_config = ConfigDict(extra="allow")

    name: str
    version: int
    actions: list[str]
    description: str | None = None
    action_descriptions: dict[str, str | None] = Field(default_factory=dict)
    created_at: datetime | None = None


class PolicyRule(BaseModel):
    """A policy rule."""

    model_config = ConfigDict(extra="allow")

    name: str
    when: dict[str, Any]
    require: str


class Policy(BaseModel):
    """A policy."""

    model_config = ConfigDict(extra="allow")

    name: str
    version: int
    description: str | None = None
    rules: list[PolicyRule] = Field(default_factory=list)


class CalibrationBucket(BaseModel):
    """One reliability bucket in a calibration report."""

    model_config = ConfigDict(extra="allow")

    lower: float
    upper: float
    count: int
    accuracy: float
    avg_confidence: float


class CalibrationReport(BaseModel):
    """A calibration report."""

    model_config = ConfigDict(extra="allow")

    sample_count: int
    brier_score: float | None = None
    expected_calibration_error: float | None = None
    buckets: list[CalibrationBucket] = Field(default_factory=list)


__all__ = [
    "CalibrationBucket",
    "CalibrationReport",
    "Decision",
    "DecisionEvent",
    "Explanation",
    "Outcome",
    "Policy",
    "PolicyRule",
    "PolicySummary",
    "Schema",
]
