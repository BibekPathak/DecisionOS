"""Persistence for decisions, their audit trail, and observed outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decisionos.engine.lifecycle import DecisionEvent
from decisionos.models import Decision, DecisionEventType, DecisionState, Outcome
from decisionos.storage.models import (
    DecisionEventRow,
    DecisionOutcomeRow,
    DecisionRow,
    PolicyEvaluationRow,
    ProviderRequestRow,
)
from decisionos.storage.repositories.mapping import (
    decision_to_domain,
    event_to_domain,
    outcome_to_domain,
    probability_rows,
)


@dataclass
class DecisionRecord:
    """Everything needed to persist one decision and its related rows."""

    decision: Decision
    decision_type: str
    model_action: str
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    state: DecisionState = DecisionState.EVALUATED
    policy_name: str | None = None
    policy_version: int | None = None
    policy_overridden: bool = False
    policy_precedence: str | None = None
    triggered_rules: list[str] = field(default_factory=list)
    events: list[DecisionEvent] = field(default_factory=list)
    provider_success: bool = True
    provider_error_kind: str | None = None
    provider_model: str | None = None


@dataclass
class DecisionFilter:
    """Filters for listing decisions (used by the dashboard and API)."""

    decision_type: str | None = None
    schema_name: str | None = None
    schema_version: int | None = None
    provider: str | None = None
    action: str | None = None
    state: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 50
    offset: int = 0


class DecisionRepository:
    """Read/write access to decisions and their related rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, record: DecisionRecord) -> Decision:
        """Persist a decision with its probabilities, events, and provenance."""
        decision = record.decision
        row = DecisionRow(
            id=decision.id,
            decision_type=record.decision_type,
            schema_name=decision.schema_name,
            schema_version=decision.schema_version,
            action=decision.action,
            model_action=record.model_action,
            confidence=decision.confidence,
            risk=decision.risk,
            reason_codes=list(decision.reason_codes),
            provider=decision.provider,
            provider_request_id=decision.provider_request_id,
            latency_ms=decision.latency_ms,
            policy_name=record.policy_name,
            policy_version=record.policy_version,
            policy_overridden=record.policy_overridden,
            state=record.state.value,
            context=record.context,
            metadata_=record.metadata,
            idempotency_key=record.idempotency_key,
            created_at=decision.created_at,
        )
        row.probabilities = probability_rows(decision)
        self._session.add(row)
        # Flush the decision and its probabilities first so rows with a
        # foreign key to ``decisions`` (events, policy evaluations, provider
        # requests) can reference it within the same transaction.
        await self._session.flush()

        for event in record.events:
            self._session.add(
                DecisionEventRow(
                    decision_id=decision.id,
                    type=event.type.value,
                    from_state=event.from_state.value if event.from_state else None,
                    to_state=event.to_state.value if event.to_state else None,
                    payload=dict(event.payload),
                    occurred_at=event.occurred_at,
                )
            )

        if record.policy_name is not None and record.policy_version is not None:
            self._session.add(
                PolicyEvaluationRow(
                    decision_id=decision.id,
                    policy_name=record.policy_name,
                    policy_version=record.policy_version,
                    precedence=record.policy_precedence or "model_decision",
                    overridden=record.policy_overridden,
                    final_action=decision.action,
                    triggered_rules=list(record.triggered_rules),
                )
            )

        self._session.add(
            ProviderRequestRow(
                decision_id=decision.id,
                provider=decision.provider,
                provider_request_id=decision.provider_request_id,
                model=record.provider_model,
                success=record.provider_success,
                error_kind=record.provider_error_kind,
                latency_ms=decision.latency_ms,
            )
        )

        await self._session.flush()
        return decision

    async def get(self, decision_id: str) -> Decision | None:
        row = await self._get_row(decision_id)
        return None if row is None else decision_to_domain(row)

    async def get_by_idempotency_key(self, key: str) -> Decision | None:
        result = await self._session.execute(
            select(DecisionRow)
            .where(DecisionRow.idempotency_key == key)
            .order_by(DecisionRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return None if row is None else decision_to_domain(row)

    async def list(self, filters: DecisionFilter | None = None) -> list[Decision]:
        filters = filters or DecisionFilter()
        statement = select(DecisionRow).order_by(DecisionRow.created_at.desc())
        if filters.decision_type:
            statement = statement.where(DecisionRow.decision_type == filters.decision_type)
        if filters.schema_name:
            statement = statement.where(DecisionRow.schema_name == filters.schema_name)
        if filters.schema_version is not None:
            statement = statement.where(DecisionRow.schema_version == filters.schema_version)
        if filters.provider:
            statement = statement.where(DecisionRow.provider == filters.provider)
        if filters.action:
            statement = statement.where(DecisionRow.action == filters.action)
        if filters.state:
            statement = statement.where(DecisionRow.state == filters.state)
        if filters.created_after is not None:
            statement = statement.where(DecisionRow.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(DecisionRow.created_at < filters.created_before)
        statement = statement.limit(filters.limit).offset(filters.offset)
        result = await self._session.execute(statement)
        return [decision_to_domain(row) for row in result.scalars().unique()]

    async def count(self, filters: DecisionFilter | None = None) -> int:
        filters = filters or DecisionFilter()
        statement = select(func.count()).select_from(DecisionRow)
        if filters.decision_type:
            statement = statement.where(DecisionRow.decision_type == filters.decision_type)
        if filters.provider:
            statement = statement.where(DecisionRow.provider == filters.provider)
        if filters.action:
            statement = statement.where(DecisionRow.action == filters.action)
        if filters.created_after is not None:
            statement = statement.where(DecisionRow.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(DecisionRow.created_at < filters.created_before)
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def get_events(self, decision_id: str) -> list[DecisionEvent]:
        result = await self._session.execute(
            select(DecisionEventRow)
            .where(DecisionEventRow.decision_id == decision_id)
            .order_by(DecisionEventRow.occurred_at, DecisionEventRow.id)
        )
        return [event_to_domain(row) for row in result.scalars()]

    async def record_outcome(self, outcome: Outcome) -> Outcome:
        row = DecisionOutcomeRow(
            decision_id=outcome.decision_id,
            actual_outcome=outcome.actual_outcome,
            success=outcome.success,
            metadata_=outcome.metadata,
            recorded_at=outcome.recorded_at,
        )
        self._session.add(row)
        # Advance the decision state and append an audit event.
        decision = await self._get_row(outcome.decision_id)
        if decision is not None:
            decision.state = DecisionState.OUTCOME_RECORDED.value
            self._session.add(
                DecisionEventRow(
                    decision_id=outcome.decision_id,
                    type=DecisionEventType.OUTCOME_RECORDED.value,
                    from_state=None,
                    to_state=DecisionState.OUTCOME_RECORDED.value,
                    payload={
                        "actual_outcome": outcome.actual_outcome,
                        "success": outcome.success,
                    },
                    occurred_at=outcome.recorded_at,
                )
            )
        await self._session.flush()
        return outcome_to_domain(row)

    async def get_outcome(self, decision_id: str) -> Outcome | None:
        result = await self._session.execute(
            select(DecisionOutcomeRow)
            .where(DecisionOutcomeRow.decision_id == decision_id)
            .order_by(DecisionOutcomeRow.recorded_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return None if row is None else outcome_to_domain(row)

    async def list_outcomes(self) -> list[Outcome]:
        result = await self._session.execute(
            select(DecisionOutcomeRow).order_by(DecisionOutcomeRow.recorded_at)
        )
        return [outcome_to_domain(row) for row in result.scalars()]

    async def _get_row(self, decision_id: str) -> DecisionRow | None:
        result = await self._session.execute(
            select(DecisionRow).where(DecisionRow.id == decision_id)
        )
        return result.scalar_one_or_none()


__all__ = ["DecisionFilter", "DecisionRecord", "DecisionRepository"]
