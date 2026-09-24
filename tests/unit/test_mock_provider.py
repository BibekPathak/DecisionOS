"""Unit tests for MockProvider: fixture matching, determinism, and validity."""

from __future__ import annotations

import pytest

from decisionos.models import DecisionRequest, DecisionSchema
from decisionos.providers import MockProvider
from decisionos.providers.fixtures import MockFixture

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


def _request(context: dict[str, object], schema: DecisionSchema = TOOL_SCHEMA) -> DecisionRequest:
    return DecisionRequest(
        decision_type="t",
        schema_name=schema.name,
        schema_version=schema.version,
        context=context,
    )


@pytest.mark.asyncio
async def test_agent_guard_spec_fixture_reproduces_expected_output() -> None:
    provider = MockProvider()
    raw = await provider.evaluate(
        _request(
            {
                "agent": "deploy-agent",
                "tool": "github.merge",
                "repository": "org/project",
                "environment": "production",
                "tests_passed": False,
            }
        ),
        TOOL_SCHEMA,
    )
    assert raw.action == "human_review"
    assert raw.confidence == 0.91
    assert raw.risk == 0.87
    assert raw.probabilities == {"allow": 0.08, "human_review": 0.91, "deny": 0.01}
    assert raw.reason_codes == [
        "production_repository",
        "merge_operation",
        "incomplete_tests",
    ]
    assert raw.provider == "mock"


@pytest.mark.asyncio
async def test_delete_database_fixture_denies() -> None:
    provider = MockProvider()
    raw = await provider.evaluate(_request({"tool": "database.delete"}), TOOL_SCHEMA)
    assert raw.action == "deny"
    assert raw.probabilities["deny"] == pytest.approx(0.97)


@pytest.mark.asyncio
async def test_read_file_fixture_allows() -> None:
    provider = MockProvider()
    raw = await provider.evaluate(_request({"tool": "read_file"}), TOOL_SCHEMA)
    assert raw.action == "allow"
    assert raw.probabilities["allow"] == pytest.approx(0.99)


@pytest.mark.asyncio
async def test_deployment_rollback_fixture() -> None:
    provider = MockProvider()
    raw = await provider.evaluate(
        _request(
            {
                "error_rate": 0.31,
                "latency_p99_ms": 2400,
                "baseline_latency_p99_ms": 320,
                "deployment_age_seconds": 180,
                "recent_deployment": True,
                "rollback_available": True,
            },
            DEPLOY_SCHEMA,
        ),
        DEPLOY_SCHEMA,
    )
    assert raw.action == "rollback"
    assert raw.probabilities["rollback"] == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_fallback_is_deterministic_across_calls() -> None:
    provider = MockProvider()
    request = _request({"tool": "some_other_tool"})
    first = await provider.evaluate(request, TOOL_SCHEMA)
    second = await provider.evaluate(request, TOOL_SCHEMA)
    assert first.probabilities == second.probabilities
    assert first.action == second.action
    assert first.reason_codes == ["mock_fallback"]


@pytest.mark.asyncio
async def test_fallback_differs_for_different_context() -> None:
    provider = MockProvider()
    a = await provider.evaluate(_request({"tool": "a"}), TOOL_SCHEMA)
    b = await provider.evaluate(_request({"tool": "b"}), TOOL_SCHEMA)
    assert a.probabilities != b.probabilities


@pytest.mark.asyncio
async def test_fallback_distribution_is_valid() -> None:
    provider = MockProvider()
    raw = await provider.evaluate(_request({"tool": "mystery"}), TOOL_SCHEMA)
    assert set(raw.probabilities) == set(TOOL_SCHEMA.actions)
    assert sum(raw.probabilities.values()) == pytest.approx(1.0)
    assert all(0.0 <= p <= 1.0 for p in raw.probabilities.values())


@pytest.mark.asyncio
async def test_fixture_is_projected_onto_schema_actions() -> None:
    # A schema that dropped 'human_review' should fold its mass into another
    # action while keeping the distribution valid.
    narrow = DecisionSchema(name="ToolAuthorization", version=2, actions=("allow", "deny"))
    provider = MockProvider()
    raw = await provider.evaluate(
        _request({"tool": "github.merge", "agent": "deploy-agent"}, narrow),
        narrow,
    )
    assert set(raw.probabilities) == set(narrow.actions)
    assert sum(raw.probabilities.values()) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_custom_fixture_set_is_used() -> None:
    fixture = MockFixture(
        action="deny",
        probabilities={"allow": 0.1, "human_review": 0.1, "deny": 0.8},
        confidence=0.8,
        risk=0.7,
        reason_codes=["custom"],
        match={"tool": "custom_tool"},
        schema_name="ToolAuthorization",
    )
    provider = MockProvider(fixtures=(fixture,))
    raw = await provider.evaluate(_request({"tool": "custom_tool"}), TOOL_SCHEMA)
    assert raw.action == "deny"
    assert raw.reason_codes == ["custom"]


@pytest.mark.asyncio
async def test_latency_override_is_reported() -> None:
    provider = MockProvider(latency_ms=12.5)
    raw = await provider.evaluate(_request({"tool": "read_file"}), TOOL_SCHEMA)
    assert raw.latency_ms == 12.5


@pytest.mark.asyncio
async def test_boolean_context_matching() -> None:
    provider = MockProvider()
    # tests_passed=False must match the fixture; tests_passed=True must not.
    match = await provider.evaluate(
        _request({"tool": "github.merge", "tests_passed": False}), TOOL_SCHEMA
    )
    non_match = await provider.evaluate(
        _request({"tool": "github.merge", "tests_passed": True}), TOOL_SCHEMA
    )
    assert match.action == "human_review"
    assert non_match.reason_codes == ["mock_fallback"]
