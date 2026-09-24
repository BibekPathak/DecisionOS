"""Conversions between ORM rows and domain models.

Keeping the mapping in one place means repositories stay thin and the domain
models remain free of persistence concerns.
"""

from __future__ import annotations

from typing import Any

from decisionos.engine.lifecycle import DecisionEvent
from decisionos.models import (
    Decision,
    DecisionEventType,
    DecisionSchema,
    DecisionState,
    Outcome,
    Policy,
)
from decisionos.storage.models import (
    DecisionEventRow,
    DecisionOutcomeRow,
    DecisionProbabilityRow,
    DecisionRow,
    DecisionSchemaRow,
    PolicyVersionRow,
)


def schema_to_domain(row: DecisionSchemaRow) -> DecisionSchema:
    return DecisionSchema(
        name=row.name,
        version=row.version,
        actions=tuple(row.actions),
        action_descriptions=dict(row.action_descriptions or {}),
        description=row.description,
        created_at=row.created_at,
    )


def policy_to_domain(row: PolicyVersionRow) -> Policy:
    return Policy.model_validate(row.definition)


def policy_definition(policy: Policy) -> dict[str, Any]:
    """Serialize a policy for storage as JSONB."""
    return policy.model_dump(mode="json")


def decision_to_domain(row: DecisionRow) -> Decision:
    probabilities = {p.action: p.probability for p in row.probabilities}
    return Decision(
        id=row.id,
        decision_type=row.decision_type,
        schema_name=row.schema_name,
        schema_version=row.schema_version,
        action=row.action,
        confidence=row.confidence,
        probabilities=probabilities,
        risk=row.risk,
        reason_codes=list(row.reason_codes or []),
        provider=row.provider,
        provider_request_id=row.provider_request_id,
        latency_ms=row.latency_ms,
        created_at=row.created_at,
    )


def probability_rows(decision: Decision) -> list[DecisionProbabilityRow]:
    return [
        DecisionProbabilityRow(action=action, probability=probability)
        for action, probability in decision.probabilities.items()
    ]


def event_to_domain(row: DecisionEventRow) -> DecisionEvent:
    return DecisionEvent(
        decision_id=row.decision_id,
        type=DecisionEventType(row.type),
        from_state=DecisionState(row.from_state) if row.from_state else None,
        to_state=DecisionState(row.to_state) if row.to_state else None,
        occurred_at=row.occurred_at,
        payload=dict(row.payload or {}),
    )


def outcome_to_domain(row: DecisionOutcomeRow) -> Outcome:
    return Outcome(
        decision_id=row.decision_id,
        actual_outcome=row.actual_outcome,
        success=row.success,
        metadata=dict(row.metadata_ or {}),
        recorded_at=row.recorded_at,
    )


__all__ = [
    "decision_to_domain",
    "event_to_domain",
    "outcome_to_domain",
    "policy_definition",
    "policy_to_domain",
    "probability_rows",
    "schema_to_domain",
]
