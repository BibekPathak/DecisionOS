"""SQLAlchemy ORM models.

Tables follow the project specification:

* ``decision_schemas`` — immutable, versioned action sets
* ``decisions`` — one row per decision
* ``decision_probabilities`` — the distribution for a decision
* ``policy_versions`` — immutable, versioned policies
* ``policy_evaluations`` — the policy outcome recorded for a decision
* ``decision_events`` — the audit trail
* ``decision_outcomes`` — observed outcomes
* ``provider_requests`` — provider call provenance

Flexible data (context, metadata, payloads) uses JSONB. Indexes are provided
for the access patterns named in the specification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decisionos.storage.database import Base


class DecisionSchemaRow(Base):
    """A persisted, immutable decision schema version."""

    __tablename__ = "decision_schemas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    actions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    action_descriptions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_decision_schemas_name_version"),
        Index("ix_decision_schemas_name", "name"),
    )


class PolicyVersionRow(Base):
    """A persisted, immutable policy version."""

    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_policy_versions_name_version"),
        Index("ix_policy_versions_name", "name"),
    )


class DecisionRow(Base):
    """A persisted decision."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    model_action: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)

    policy_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    policy_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)

    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    probabilities: Mapped[list[DecisionProbabilityRow]] = relationship(
        back_populates="decision", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_decisions_created_at", "created_at"),
        Index("ix_decisions_schema", "schema_name", "schema_version"),
        Index("ix_decisions_decision_type", "decision_type"),
        Index("ix_decisions_provider", "provider"),
        Index("ix_decisions_action", "action"),
        Index("ix_decisions_state", "state"),
        Index("ix_decisions_idempotency_key", "idempotency_key"),
    )


class DecisionProbabilityRow(Base):
    """One probability entry within a decision's distribution."""

    __tablename__ = "decision_probabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)

    decision: Mapped[DecisionRow] = relationship(back_populates="probabilities")

    __table_args__ = (
        UniqueConstraint("decision_id", "action", name="uq_decision_probabilities_decision_action"),
        Index("ix_decision_probabilities_decision_id", "decision_id"),
    )


class PolicyEvaluationRow(Base):
    """The policy outcome recorded for a decision."""

    __tablename__ = "policy_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )
    policy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    precedence: Mapped[str] = mapped_column(String(32), nullable=False)
    overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    final_action: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_rules: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_policy_evaluations_decision_id", "decision_id"),
        Index("ix_policy_evaluations_policy", "policy_name", "policy_version"),
    )


class DecisionEventRow(Base):
    """An audit event in a decision's history."""

    __tablename__ = "decision_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_decision_events_decision_id", "decision_id"),
        Index("ix_decision_events_occurred_at", "occurred_at"),
    )


class DecisionOutcomeRow(Base):
    """An observed outcome for a decision."""

    __tablename__ = "decision_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )
    actual_outcome: Mapped[str] = mapped_column(String(255), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_decision_outcomes_decision_id", "decision_id"),
        Index("ix_decision_outcomes_recorded_at", "recorded_at"),
    )


class ProviderRequestRow(Base):
    """Provenance for a single provider call."""

    __tablename__ = "provider_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_provider_requests_decision_id", "decision_id"),
        Index("ix_provider_requests_provider", "provider"),
        Index("ix_provider_requests_created_at", "created_at"),
    )


__all__ = [
    "DecisionEventRow",
    "DecisionOutcomeRow",
    "DecisionProbabilityRow",
    "DecisionRow",
    "DecisionSchemaRow",
    "PolicyEvaluationRow",
    "PolicyVersionRow",
    "ProviderRequestRow",
]
