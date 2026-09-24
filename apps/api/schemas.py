"""API request and response models.

These are the wire contracts. They are deliberately separate from the domain
models so the HTTP surface can evolve (or stay stable) independently of
internal representation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- Decisions -------------------------------------------------------------


class CreateDecisionRequest(BaseModel):
    """Body for ``POST /v1/decisions``."""

    model_config = ConfigDict(extra="forbid")

    decision_type: str = Field(min_length=1, max_length=128)
    schema_name: str = Field(min_length=1, max_length=128)
    schema_version: int = Field(ge=1)
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = Field(default=None, max_length=64)
    policy: str | None = Field(default=None, max_length=160)


class PolicySummary(BaseModel):
    """Policy outcome included in a decision response."""

    name: str
    version: int
    precedence: str
    overridden: bool
    triggered_rules: list[str] = Field(default_factory=list)


class DecisionResponse(BaseModel):
    """Response for decision creation and retrieval."""

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


class RecordOutcomeRequest(BaseModel):
    """Body for ``POST /v1/decisions/{id}/outcome``."""

    model_config = ConfigDict(extra="forbid")

    actual_outcome: str = Field(min_length=1, max_length=255)
    success: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutcomeResponse(BaseModel):
    """Response for a recorded outcome."""

    decision_id: str
    actual_outcome: str
    success: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime


class DecisionEventResponse(BaseModel):
    """A single audit event."""

    type: str
    from_state: str | None = None
    to_state: str | None = None
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ExplanationResponse(BaseModel):
    """Structured evidence for a decision.

    Contains only observed facts: the model distribution, its reason codes,
    the policy rules that fired, and provenance. No generated prose.
    """

    decision_id: str
    decision: str
    model_action: str
    model_probabilities: dict[str, float]
    confidence: float
    risk: float | None
    reason_codes: list[str]
    policy_rules_triggered: list[str]
    policy_precedence: str | None
    provider: str
    schema_name: str
    schema_version: int
    lifecycle: list[DecisionEventResponse] = Field(default_factory=list)


# --- Schemas ---------------------------------------------------------------


class CreateSchemaRequest(BaseModel):
    """Body for ``POST /v1/schemas``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    version: int = Field(default=1, ge=1)
    actions: tuple[str, ...] = Field(min_length=1)
    description: str | None = None
    action_descriptions: dict[str, str | None] = Field(default_factory=dict)


class SchemaResponse(BaseModel):
    """A decision schema."""

    name: str
    version: int
    actions: list[str]
    description: str | None = None
    action_descriptions: dict[str, str | None] = Field(default_factory=dict)
    created_at: datetime


# --- Policies --------------------------------------------------------------


class CreatePolicyRequest(BaseModel):
    """Body for ``POST /v1/policies``.

    ``rules`` is the same structure used in the YAML policy format.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    version: int = Field(default=1, ge=1)
    rules: list[dict[str, Any]] = Field(min_length=1)
    description: str | None = None
    action_precedence: dict[str, str] = Field(default_factory=dict)


class PolicyRuleResponse(BaseModel):
    name: str
    when: dict[str, Any]
    require: str


class PolicyResponse(BaseModel):
    """A policy."""

    name: str
    version: int
    description: str | None = None
    rules: list[PolicyRuleResponse]
    created_at: datetime | None = None


# --- Calibration -----------------------------------------------------------


class CalibrationBucket(BaseModel):
    lower: float
    upper: float
    count: int
    accuracy: float
    avg_confidence: float


class CalibrationResponse(BaseModel):
    sample_count: int
    brier_score: float | None = None
    expected_calibration_error: float | None = None
    buckets: list[CalibrationBucket] = Field(default_factory=list)


# --- Errors ----------------------------------------------------------------


class ErrorResponse(BaseModel):
    """A structured error body."""

    error: str
    detail: str
    request_id: str | None = None


__all__ = [
    "CalibrationBucket",
    "CalibrationResponse",
    "CreateDecisionRequest",
    "CreatePolicyRequest",
    "CreateSchemaRequest",
    "DecisionEventResponse",
    "DecisionResponse",
    "ErrorResponse",
    "ExplanationResponse",
    "OutcomeResponse",
    "PolicyResponse",
    "PolicyRuleResponse",
    "PolicySummary",
    "RecordOutcomeRequest",
    "SchemaResponse",
]
