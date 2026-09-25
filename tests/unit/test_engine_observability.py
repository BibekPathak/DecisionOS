"""Tests that the decision engine emits observability signals."""

from __future__ import annotations

import pytest

from decisionos.config import Settings
from decisionos.engine import DecisionEvaluator, InMemorySchemaResolver
from decisionos.models import DecisionRequest, DecisionSchema
from decisionos.observability.metrics import render_metrics
from decisionos.policies import PolicyEvaluator, load_policy_yaml
from decisionos.providers import get_registry, reset_registry

SCHEMA = DecisionSchema(
    name="ToolAuthorization",
    version=1,
    actions=("allow", "human_review", "deny"),
)

POLICY = load_policy_yaml(
    """
    name: engine-observability-policy
    rules:
      - name: high-risk
        when:
          risk: {gt: 0.9}
        action:
          require: deny
    """
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_registry()
    yield
    reset_registry()


def _evaluator() -> DecisionEvaluator:
    registry = get_registry(Settings(_env_file=None))
    return DecisionEvaluator(
        registry, InMemorySchemaResolver([SCHEMA]), id_factory=lambda: "dec_obs"
    )


def _request(context: dict[str, object]) -> DecisionRequest:
    return DecisionRequest(
        decision_type="obs_type",
        schema_name="ToolAuthorization",
        schema_version=1,
        context=context,
    )


@pytest.mark.asyncio
async def test_evaluation_records_metrics() -> None:
    evaluator = _evaluator()
    await evaluator.evaluate(_request({"tool": "read_file"}))
    text = render_metrics()
    assert "decisionos_decisions_total{" in text
    assert 'decision_type="obs_type"' in text
    assert 'decisionos_provider_latency_seconds_count{provider="mock"}' in text


@pytest.mark.asyncio
async def test_policy_override_records_metric() -> None:
    evaluator = _evaluator()
    policy = PolicyEvaluator(POLICY, SCHEMA)
    # Force a high derived risk via the mock delete-database fixture (risk 0.95).
    await evaluator.evaluate(_request({"tool": "database.delete"}), policy_evaluator=policy)
    text = render_metrics()
    assert "decisionos_policy_overrides_total" in text


@pytest.mark.asyncio
async def test_context_is_reset_after_evaluation() -> None:
    from decisionos.observability.context import get_request_context

    evaluator = _evaluator()
    await evaluator.evaluate(_request({"tool": "read_file"}))
    assert get_request_context().decision_id is None
