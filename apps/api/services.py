"""Service layer.

Routes are thin; all orchestration lives here. Services compose the engine,
policy engine, and repositories, translating between API schemas and domain
models. They never contain provider-specific behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.schemas import (
    CalibrationBucket,
    CalibrationResponse,
    CreateDecisionRequest,
    CreatePolicyRequest,
    CreateSchemaRequest,
    DecisionEventResponse,
    DecisionResponse,
    ExplanationResponse,
    OutcomeResponse,
    PolicyResponse,
    PolicyRuleResponse,
    PolicySummary,
    RecordOutcomeRequest,
    SchemaResponse,
)
from decisionos.calibration import (
    CalibrationEvaluator,
    CalibrationFilter,
    DatabaseCalibrationSource,
)
from decisionos.engine import (
    DecisionEvaluator,
    EvaluationResult,
    SchemaNotFoundError,
)
from decisionos.models import (
    Decision,
    DecisionRequest,
    DecisionSchema,
    DecisionState,
    Outcome,
    Policy,
)
from decisionos.observability.metrics import set_calibration_error
from decisionos.policies import PolicyEvaluator, PolicyNotFoundError
from decisionos.storage import (
    DecisionFilter,
    DecisionRecord,
    DecisionRepository,
    DecisionSchemaRepository,
    PolicyRepository,
)


class DecisionNotFoundError(LookupError):
    """Raised when a decision id does not exist."""

    def __init__(self, decision_id: str) -> None:
        super().__init__(f"decision {decision_id!r} not found")
        self.decision_id = decision_id


class InvalidPolicyError(ValueError):
    """Raised when a requested policy cannot be resolved or evaluated."""


@dataclass
class CreatedDecision:
    """A created decision and whether it was newly created (vs. idempotent)."""

    response: DecisionResponse
    created: bool


class DecisionService:
    """Creates and reads decisions and outcomes."""

    def __init__(
        self,
        *,
        evaluator: DecisionEvaluator,
        decisions: DecisionRepository,
        schemas: DecisionSchemaRepository,
        policies: PolicyRepository,
    ) -> None:
        self._evaluator = evaluator
        self._decisions = decisions
        self._schemas = schemas
        self._policies = policies

    async def create(self, request: CreateDecisionRequest) -> CreatedDecision:
        """Evaluate and persist a new decision."""
        domain_request = DecisionRequest(
            decision_type=request.decision_type,
            schema_name=request.schema_name,
            schema_version=request.schema_version,
            context=request.context,
            metadata=request.metadata,
            provider=request.provider,
            policy=request.policy,
            idempotency_key=None,
        )

        policy, policy_evaluator = await self._resolve_policy(request)
        result = await self._evaluator.evaluate(domain_request, policy_evaluator=policy_evaluator)

        model_action = (
            result.model_decision.action
            if result.model_decision is not None
            else result.decision.action
        )
        record = DecisionRecord(
            decision=result.decision,
            decision_type=request.decision_type,
            model_action=model_action,
            context=request.context,
            metadata=request.metadata,
            state=_final_state(result),
            policy_name=policy.name if policy else None,
            policy_version=policy.version if policy else None,
            policy_overridden=result.overridden,
            policy_precedence=result.precedence,
            triggered_rules=list(result.triggered_rules),
            events=list(result.events),
        )
        await self._decisions.save(record)
        return CreatedDecision(response=self._to_response(result, policy), created=True)

    async def get(self, decision_id: str) -> DecisionResponse:
        row = await self._decisions.get(decision_id)
        if row is None:
            raise DecisionNotFoundError(decision_id)
        return self._to_response_from_row(row)

    async def list(self, filters: DecisionFilter) -> list[DecisionResponse]:
        rows = await self._decisions.list(filters)
        return [self._to_response_from_row(row) for row in rows]

    async def record_outcome(
        self, decision_id: str, request: RecordOutcomeRequest
    ) -> OutcomeResponse:
        decision = await self._decisions.get(decision_id)
        if decision is None:
            raise DecisionNotFoundError(decision_id)
        outcome = Outcome(
            decision_id=decision_id,
            actual_outcome=request.actual_outcome,
            success=request.success,
            metadata=request.metadata,
        )
        await self._decisions.record_outcome(outcome)
        return OutcomeResponse(
            decision_id=outcome.decision_id,
            actual_outcome=outcome.actual_outcome,
            success=outcome.success,
            metadata=outcome.metadata,
            recorded_at=outcome.recorded_at,
        )

    async def explanation(self, decision_id: str) -> ExplanationResponse:
        decision = await self._decisions.get(decision_id)
        if decision is None:
            raise DecisionNotFoundError(decision_id)
        events = await self._decisions.get_events(decision_id)
        policy_evaluation = await self._policy_evaluation(decision_id)
        precedence = policy_evaluation.precedence if policy_evaluation else None
        triggered = policy_evaluation.triggered_rules if policy_evaluation else []
        return ExplanationResponse(
            decision_id=decision.id,
            decision=decision.action,
            model_action=decision.action,
            model_probabilities=decision.probabilities,
            confidence=decision.confidence,
            risk=decision.risk,
            reason_codes=decision.reason_codes,
            policy_rules_triggered=list(triggered),
            policy_precedence=precedence,
            provider=decision.provider,
            schema_name=decision.schema_name,
            schema_version=decision.schema_version,
            lifecycle=[
                DecisionEventResponse(
                    type=event.type.value,
                    from_state=event.from_state.value if event.from_state else None,
                    to_state=event.to_state.value if event.to_state else None,
                    occurred_at=event.occurred_at,
                    payload=event.payload,
                )
                for event in events
            ],
        )

    # -- helpers ----------------------------------------------------------

    async def _resolve_policy(
        self, request: CreateDecisionRequest
    ) -> tuple[Policy | None, PolicyEvaluator | None]:
        if not request.policy:
            return None, None
        try:
            policy = await self._policies.get_by_key(request.policy)
        except PolicyNotFoundError as error:
            raise InvalidPolicyError(str(error)) from error
        try:
            schema = await self._schemas.get(request.schema_name, request.schema_version)
        except SchemaNotFoundError:
            schema = None
        try:
            evaluator = PolicyEvaluator(policy, schema)
        except ValueError as error:
            raise InvalidPolicyError(str(error)) from error
        return policy, evaluator

    async def _policy_evaluation(self, decision_id: str):
        return await self._decisions.get_policy_evaluation(decision_id)

    def _to_response(self, result: EvaluationResult, policy: Policy | None) -> DecisionResponse:
        decision = result.decision
        return DecisionResponse(
            decision_id=decision.id,
            decision_type=decision.decision_type,
            schema_name=decision.schema_name,
            schema_version=decision.schema_version,
            action=decision.action,
            model_action=(
                result.model_decision.action
                if result.model_decision is not None
                else decision.action
            ),
            confidence=decision.confidence,
            probabilities=decision.probabilities,
            risk=decision.risk,
            reason_codes=decision.reason_codes,
            provider=decision.provider,
            provider_request_id=decision.provider_request_id,
            latency_ms=decision.latency_ms,
            state=_final_state(result).value,
            policy=_policy_summary(result, policy),
            created_at=decision.created_at,
        )

    def _to_response_from_row(self, decision: Decision) -> DecisionResponse:
        return DecisionResponse(
            decision_id=decision.id,
            decision_type=decision.decision_type,
            schema_name=decision.schema_name,
            schema_version=decision.schema_version,
            action=decision.action,
            model_action=decision.action,
            confidence=decision.confidence,
            probabilities=decision.probabilities,
            risk=decision.risk,
            reason_codes=decision.reason_codes,
            provider=decision.provider,
            provider_request_id=decision.provider_request_id,
            latency_ms=decision.latency_ms,
            state=None,
            policy=None,
            created_at=decision.created_at,
        )


def _final_state(result: EvaluationResult) -> DecisionState:
    if result.triggered_rules or result.overridden:
        return DecisionState.ACTION_SELECTED
    return DecisionState.EVALUATED


def _policy_summary(result: EvaluationResult, policy: Policy | None) -> PolicySummary | None:
    if policy is None:
        return None
    return PolicySummary(
        name=policy.name,
        version=policy.version,
        precedence=result.precedence or "model_decision",
        overridden=result.overridden,
        triggered_rules=list(result.triggered_rules),
    )


class SchemaService:
    """Creates and reads decision schemas."""

    def __init__(self, schemas: DecisionSchemaRepository) -> None:
        self._schemas = schemas

    async def create(self, request: CreateSchemaRequest) -> SchemaResponse:
        schema = DecisionSchema(
            name=request.name,
            version=request.version,
            actions=tuple(request.actions),
            description=request.description,
            action_descriptions=dict(request.action_descriptions),
        )
        stored = await self._schemas.add(schema)
        return self._to_response(stored)

    async def get(self, name: str, version: int) -> SchemaResponse:
        return self._to_response(await self._schemas.get(name, version))

    async def list(self) -> list[SchemaResponse]:
        return [self._to_response(schema) for schema in await self._schemas.list_all()]

    @staticmethod
    def _to_response(schema: DecisionSchema) -> SchemaResponse:
        return SchemaResponse(
            name=schema.name,
            version=schema.version,
            actions=list(schema.actions),
            description=schema.description,
            action_descriptions=dict(schema.action_descriptions),
            created_at=schema.created_at,
        )


class PolicyService:
    """Creates and reads policies."""

    def __init__(self, policies: PolicyRepository) -> None:
        self._policies = policies

    async def create(self, request: CreatePolicyRequest) -> PolicyResponse:
        try:
            policy = Policy.model_validate(
                {
                    "name": request.name,
                    "version": request.version,
                    "rules": request.rules,
                    "description": request.description,
                    "action_precedence": request.action_precedence,
                }
            )
        except ValueError as error:
            raise InvalidPolicyError(str(error)) from error
        stored = await self._policies.add(policy)
        return self._to_response(stored)

    async def get(self, key: str) -> PolicyResponse:
        try:
            policy = await self._policies.get_by_key(key)
        except PolicyNotFoundError as error:
            raise DecisionNotFoundError(key) from error
        return self._to_response(policy)

    async def list(self) -> list[PolicyResponse]:
        return [self._to_response(policy) for policy in await self._policies.list_all()]

    @staticmethod
    def _to_response(policy: Policy) -> PolicyResponse:
        return PolicyResponse(
            name=policy.name,
            version=policy.version,
            description=policy.description,
            rules=[
                PolicyRuleResponse(name=rule.name, when=rule.when, require=rule.action.require)
                for rule in policy.rules
            ],
        )


class CalibrationService:
    """Computes calibration from stored decisions and their outcomes.

    The report contains only measured statistics over decisions that have a
    recorded outcome; there are no synthetic numbers.
    """

    def __init__(self, source: DatabaseCalibrationSource) -> None:
        self._evaluator = CalibrationEvaluator(source)

    async def report(self, filter: CalibrationFilter | None = None) -> CalibrationResponse:
        report = await self._evaluator.report(filter)
        if report.expected_calibration_error is not None:
            set_calibration_error(
                decision_type=(filter.decision_type if filter else None) or "all",
                value=report.expected_calibration_error,
            )
        return CalibrationResponse(
            sample_count=report.sample_count,
            brier_score=report.brier_score,
            expected_calibration_error=report.expected_calibration_error,
            buckets=[
                CalibrationBucket(
                    lower=bucket.lower,
                    upper=bucket.upper,
                    count=bucket.count,
                    accuracy=bucket.accuracy,
                    avg_confidence=bucket.avg_confidence,
                )
                for bucket in report.buckets
            ],
        )


__all__ = [
    "CalibrationService",
    "CreatedDecision",
    "DecisionNotFoundError",
    "DecisionService",
    "InvalidPolicyError",
    "PolicyService",
    "SchemaService",
]
