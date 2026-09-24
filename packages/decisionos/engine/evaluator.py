"""Decision evaluation.

The evaluator is the orchestrator that turns a :class:`DecisionRequest` into a
validated :class:`Decision`:

1. validate the request (context size),
2. resolve the target :class:`DecisionSchema`,
3. obtain a provider from the registry,
4. call the provider to obtain a probability distribution,
5. validate that distribution across the provider trust boundary, producing a
   :class:`Decision`,
6. derive additional signal (risk, reason codes) where the provider did not
   supply it,
7. hand the decision to the policy engine when one is supplied.

The evaluator owns no provider-specific behaviour. It depends on the
:class:`~decisionos.providers.base.DecisionProvider` interface and a
:class:`SchemaResolver`, both of which are injected.

Policy evaluation is optional here so Phase 3 can run standalone; Phase 4
injects a policy evaluator and this module advances the lifecycle through the
policy and action-selection states.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from decisionos.models import (
    Decision,
    DecisionRequest,
    DecisionSchema,
    ProviderOutputError,
    RawDecision,
)
from decisionos.observability.logging import get_logger
from decisionos.providers.base import DecisionProvider, ProviderError
from decisionos.providers.registry import ProviderRegistry

logger = get_logger(__name__)


class SchemaNotFoundError(LookupError):
    """Raised when a request references a schema that does not exist."""

    def __init__(self, name: str, version: int) -> None:
        super().__init__(f"schema {name!r} version {version} not found")
        self.name = name
        self.version = version


@runtime_checkable
class SchemaResolver(Protocol):
    """Resolves a schema by name and version."""

    async def resolve(self, name: str, version: int) -> DecisionSchema: ...


class InMemorySchemaResolver:
    """An in-memory schema catalog.

    Phase 5 provides a database-backed resolver implementing the same protocol.
    """

    def __init__(self, schemas: list[DecisionSchema] | None = None) -> None:
        self._schemas: dict[tuple[str, int], DecisionSchema] = {}
        for schema in schemas or []:
            self.register(schema)

    def register(self, schema: DecisionSchema) -> None:
        """Add a schema to the catalog. Schemas are immutable once registered."""
        key = (schema.name, schema.version)
        existing = self._schemas.get(key)
        if existing is not None and existing != schema:
            raise ValueError(f"schema {schema.key} already registered with different content")
        self._schemas[key] = schema

    async def resolve(self, name: str, version: int) -> DecisionSchema:
        try:
            return self._schemas[(name, version)]
        except KeyError as error:
            raise SchemaNotFoundError(name, version) from error


class PolicyEvaluationLike(Protocol):
    """Structural view of a policy evaluator (implemented in Phase 4).

    Kept minimal to avoid a dependency cycle: the evaluator needs only to call
    ``evaluate`` with a decision and the request context, and to read back the
    final action, triggered rule names, and whether the model was overridden.
    """

    async def evaluate(self, decision: Decision, context: dict[str, object]) -> PolicyOutcome: ...


@dataclass(frozen=True)
class PolicyOutcome:
    """The result of applying a policy to a model decision.

    Attributes
    ----------
    decision:
        The decision after policy enforcement (action may have changed).
    triggered_rules:
        Names of rules that fired.
    precedence:
        The precedence that determined the final action.
    overridden:
        Whether policy changed the model's suggested action.
    """

    decision: Decision
    triggered_rules: list[str] = field(default_factory=list)
    precedence: str = "model_decision"
    overridden: bool = False


@dataclass
class EvaluationResult:
    """The outcome of evaluating a request.

    Attributes
    ----------
    decision:
        The validated (and, if a policy ran, policy-resolved) decision.
    model_decision:
        The model's decision before any policy was applied. Equal to
        ``decision`` when no policy ran or the policy did not override.
    events:
        The audit trail produced while evaluating.
    overridden:
        Whether policy overrode the model's suggested action.
    triggered_rules:
        Policy rules that fired.
    """

    decision: Decision
    model_decision: Decision | None = None
    events: list = field(default_factory=list)
    overridden: bool = False
    triggered_rules: list[str] = field(default_factory=list)
    precedence: str | None = None


class DecisionEvaluator:
    """Evaluates decision requests against a provider and optional policy.

    Parameters
    ----------
    registry:
        Resolves providers by name.
    schema_resolver:
        Resolves schemas by name and version.
    id_factory:
        Optional decision-id generator, primarily for deterministic tests.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        schema_resolver: SchemaResolver,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._registry = registry
        self._schemas = schema_resolver
        self._id_factory = id_factory or _new_decision_id

    async def evaluate(
        self,
        request: DecisionRequest,
        policy_evaluator: PolicyEvaluationLike | None = None,
    ) -> EvaluationResult:
        """Evaluate ``request`` and return an :class:`EvaluationResult`.

        Raises
        ------
        ValueError
            If the request context exceeds its size limit.
        SchemaNotFoundError
            If the schema does not exist.
        ProviderError
            If the provider fails. The error carries a retryable kind.
        ProviderOutputError
            If the provider output fails validation at the trust boundary.
        """
        from decisionos.engine.lifecycle import DecisionLifecycle

        request.validate_context_size()

        lifecycle = DecisionLifecycle(self._id_factory())
        schema = await self._schemas.resolve(request.schema_name, request.schema_version)

        provider: DecisionProvider = self._registry.get(request.provider)
        lifecycle.start_evaluation(
            provider=provider.name,
            schema_key=schema.key,
        )

        started = time.perf_counter()
        try:
            raw = await provider.evaluate(request, schema)
        except ProviderError as error:
            lifecycle.fail(
                error_kind=error.kind,
                provider=error.provider,
                message=str(error),
            )
            raise
        provider_elapsed_ms = (time.perf_counter() - started) * 1000.0

        decision = self._build_decision(
            raw,
            request=request,
            schema=schema,
            decision_id=lifecycle.decision_id,
        )
        lifecycle.complete_evaluation(
            action=decision.action,
            confidence=decision.confidence,
            provider_elapsed_ms=round(provider_elapsed_ms, 3),
        )

        result = EvaluationResult(
            decision=decision,
            model_decision=decision,
            events=list(lifecycle.events),
        )

        if policy_evaluator is not None:
            outcome = await policy_evaluator.evaluate(decision, dict(request.context))
            lifecycle.complete_policy_evaluation(
                precedence=outcome.precedence,
                triggered_rules=outcome.triggered_rules,
            )
            lifecycle.select_action(action=outcome.decision.action)
            result.decision = outcome.decision
            result.overridden = outcome.overridden
            result.triggered_rules = list(outcome.triggered_rules)
            result.precedence = outcome.precedence
            result.events = list(lifecycle.events)

        return result

    def _build_decision(
        self,
        raw: RawDecision,
        *,
        request: DecisionRequest,
        schema: DecisionSchema,
        decision_id: str,
    ) -> Decision:
        try:
            decision = Decision.from_raw(
                raw,
                decision_id=decision_id,
                decision_type=request.decision_type,
                schema=schema,
                context=request.context,
            )
        except ProviderOutputError:
            logger.warning(
                "decision.provider_output_invalid",
                provider=raw.provider,
                decision_id=decision_id,
                schema_key=schema.key,
            )
            raise
        return self._derive_signals(decision, schema)

    @staticmethod
    def _derive_signals(decision: Decision, schema: DecisionSchema) -> Decision:
        """Add schema-derived reason codes without fabricating explanations.

        Reason codes are only ever *derived from known inputs*: the provider's
        own codes (already attached) and the schema's declared
        ``action_descriptions``. No explanation text is invented.
        """
        derived: list[str] = list(decision.reason_codes)
        description = schema.action_descriptions.get(decision.action)
        if description and description not in derived:
            derived.append(description)
        if derived == decision.reason_codes:
            return decision
        return decision.model_copy(update={"reason_codes": derived})


def _new_decision_id() -> str:
    return f"dec_{uuid.uuid4().hex}"


__all__ = [
    "DecisionEvaluator",
    "EvaluationResult",
    "InMemorySchemaResolver",
    "PolicyEvaluationLike",
    "PolicyOutcome",
    "SchemaNotFoundError",
    "SchemaResolver",
]
