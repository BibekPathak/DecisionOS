"""Unit tests for DecisionEvaluator and the schema resolver."""

from __future__ import annotations

import pytest

from decisionos.config import Settings
from decisionos.engine import (
    DecisionEvaluator,
    InMemorySchemaResolver,
    SchemaNotFoundError,
)
from decisionos.models import (
    DecisionEventType,
    DecisionRequest,
    DecisionSchema,
    DecisionState,
    ProviderOutputError,
    RawDecision,
)
from decisionos.providers import ProviderError, get_registry, reset_registry

TOOL_SCHEMA = DecisionSchema(
    name="ToolAuthorization",
    version=1,
    actions=("allow", "human_review", "deny"),
)
DEPLOY_SCHEMA = DecisionSchema(
    name="DeploymentDecision",
    version=1,
    actions=("continue", "rollback", "pause", "human_review"),
)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    reset_registry()
    yield
    reset_registry()


def _evaluator(*schemas: DecisionSchema, decision_id: str = "dec_test") -> DecisionEvaluator:
    registry = get_registry(Settings(_env_file=None))
    resolver = InMemorySchemaResolver(list(schemas) or [TOOL_SCHEMA])
    return DecisionEvaluator(registry, resolver, id_factory=lambda: decision_id)


def _request(
    context: dict[str, object], schema: DecisionSchema = TOOL_SCHEMA, **overrides: object
) -> DecisionRequest:
    base: dict[str, object] = {
        "decision_type": "tool_authorization",
        "schema_name": schema.name,
        "schema_version": schema.version,
        "context": context,
    }
    base.update(overrides)
    return DecisionRequest(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_evaluate_produces_validated_decision() -> None:
    evaluator = _evaluator(TOOL_SCHEMA)
    result = await evaluator.evaluate(
        _request(
            {
                "agent": "deploy-agent",
                "tool": "github.merge",
                "repository": "org/project",
                "environment": "production",
                "tests_passed": False,
            }
        )
    )
    assert result.decision.id == "dec_test"
    assert result.decision.action == "human_review"
    assert result.decision.confidence == 0.91
    assert result.decision.risk == 0.87
    assert result.decision.provider == "mock"
    assert result.overridden is False


@pytest.mark.asyncio
async def test_evaluate_advances_lifecycle_to_evaluated() -> None:
    evaluator = _evaluator(TOOL_SCHEMA)
    result = await evaluator.evaluate(_request({"tool": "read_file"}))
    states = [event.to_state for event in result.events]
    assert states == [
        DecisionState.CREATED,
        DecisionState.EVALUATING,
        DecisionState.EVALUATED,
    ]
    assert result.events[-1].type is DecisionEventType.EVALUATION_COMPLETED


@pytest.mark.asyncio
async def test_schema_derived_reason_codes_are_appended() -> None:
    schema = DecisionSchema(
        name="ToolAuthorization",
        version=1,
        actions=("allow", "deny"),
        action_descriptions={"allow": "Permitted"},
    )
    evaluator = _evaluator(schema)
    result = await evaluator.evaluate(_request({"tool": "read_file"}, schema))
    assert "read_only_operation" in result.decision.reason_codes
    assert "Permitted" in result.decision.reason_codes


@pytest.mark.asyncio
async def test_unknown_schema_raises() -> None:
    evaluator = _evaluator(TOOL_SCHEMA)
    with pytest.raises(SchemaNotFoundError):
        await evaluator.evaluate(_request({}, schema=TOOL_SCHEMA, schema_name="Missing"))


@pytest.mark.asyncio
async def test_context_size_limit_enforced() -> None:
    evaluator = _evaluator(TOOL_SCHEMA)
    with pytest.raises(ValueError, match="exceeding the limit"):
        await evaluator.evaluate(_request({"blob": "x" * 100}, max_context_bytes=10))


@pytest.mark.asyncio
async def test_provider_failure_propagates_typed_error() -> None:
    registry = get_registry(Settings(_env_file=None))

    class Broken:
        name = "broken"

        async def evaluate(self, request: DecisionRequest, schema: DecisionSchema) -> RawDecision:
            raise ProviderError("boom", provider="broken")

    registry.register("broken", lambda _settings: Broken())
    evaluator = DecisionEvaluator(
        registry, InMemorySchemaResolver([TOOL_SCHEMA]), id_factory=lambda: "dec_test"
    )
    with pytest.raises(ProviderError, match="boom"):
        await evaluator.evaluate(_request({}, provider="broken"))


@pytest.mark.asyncio
async def test_provider_output_invalid_is_rejected() -> None:
    registry = get_registry(Settings(_env_file=None))

    class BadOutput:
        name = "bad"

        async def evaluate(self, request: DecisionRequest, schema: DecisionSchema) -> RawDecision:
            return RawDecision(
                action="not_in_schema",
                probabilities={"allow": 0.5, "deny": 0.5},
                confidence=0.5,
                provider="bad",
                latency_ms=1.0,
            )

    registry.register("bad", lambda _settings: BadOutput())
    evaluator = DecisionEvaluator(
        registry, InMemorySchemaResolver([TOOL_SCHEMA]), id_factory=lambda: "dec_test"
    )
    with pytest.raises(ProviderOutputError):
        await evaluator.evaluate(_request({}, provider="bad"))


@pytest.mark.asyncio
async def test_evaluator_uses_requested_provider() -> None:
    evaluator = _evaluator(DEPLOY_SCHEMA)
    result = await evaluator.evaluate(
        _request(
            {
                "recent_deployment": True,
                "rollback_available": True,
                "error_rate": 0.31,
            },
            DEPLOY_SCHEMA,
            provider="mock",
        )
    )
    assert result.decision.provider == "mock"
    assert result.decision.action == "rollback"


def test_schema_resolver_registers_and_resolves() -> None:
    resolver = InMemorySchemaResolver([TOOL_SCHEMA])
    import asyncio

    resolved = asyncio.run(resolver.resolve("ToolAuthorization", 1))
    assert resolved == TOOL_SCHEMA


def test_schema_resolver_rejects_conflicting_duplicate() -> None:
    resolver = InMemorySchemaResolver([TOOL_SCHEMA])
    with pytest.raises(ValueError, match="already registered"):
        resolver.register(
            DecisionSchema(name="ToolAuthorization", version=1, actions=("allow", "deny"))
        )


def test_schema_resolver_allows_identical_duplicate() -> None:
    resolver = InMemorySchemaResolver([TOOL_SCHEMA])
    resolver.register(TOOL_SCHEMA)  # idempotent
