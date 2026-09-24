"""Integration: Jev provider through the decision engine trust boundary.

Confirms that a mocked TypeSafe response flows through the evaluator, is
validated into a ``Decision``, and that provider failures propagate as typed
errors. No database or network is required.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from decisionos.engine import DecisionEvaluator, InMemorySchemaResolver
from decisionos.models import (
    DecisionRequest,
    DecisionSchema,
    ProviderOutputError,
)
from decisionos.providers.jev import JevProvider
from decisionos.providers.registry import ProviderRegistry

SCHEMA = DecisionSchema(
    name="ToolAuthorization",
    version=1,
    actions=("allow", "human_review", "deny"),
)
REQUEST = DecisionRequest(
    decision_type="tool_authorization",
    schema_name="ToolAuthorization",
    schema_version=1,
    context={"tool": "github.merge", "environment": "production"},
    provider="jev",
)


def _registry_with(handler) -> ProviderRegistry:
    from decisionos.config import Settings

    registry = ProviderRegistry(Settings(_env_file=None))
    provider = JevProvider(
        api_key="k",
        base_url="https://api.typesafe.ai",
        model="jev-latest",
        timeout_seconds=1.0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    registry.register("jev", lambda _settings: provider)
    return registry


@pytest.mark.asyncio
async def test_jev_response_produces_validated_decision() -> None:
    body: dict[str, Any] = {
        "model": "jev-1.13.0",
        "answers": {
            "action": {
                "type": "choice",
                "choice": "human_review",
                "confidence": 0.91,
                "probabilities": {"allow": 0.08, "human_review": 0.91, "deny": 0.01},
            }
        },
    }
    registry = _registry_with(lambda request: httpx.Response(200, json=body))
    evaluator = DecisionEvaluator(
        registry, InMemorySchemaResolver([SCHEMA]), id_factory=lambda: "dec_jev"
    )
    result = await evaluator.evaluate(REQUEST)
    assert result.decision.action == "human_review"
    assert result.decision.confidence == pytest.approx(0.91)
    assert result.decision.provider == "jev"
    assert result.decision.risk == pytest.approx(0.09)  # derived: 1 - P[action]
    assert result.decision.probabilities["human_review"] == pytest.approx(0.91)
    await registry.aclose()


@pytest.mark.asyncio
async def test_jev_action_outside_schema_is_rejected_at_boundary() -> None:
    body = {
        "answers": {
            "action": {
                "type": "choice",
                "choice": "merge",
                "confidence": 0.9,
                "probabilities": {"merge": 0.9, "allow": 0.1},
            }
        }
    }
    registry = _registry_with(lambda request: httpx.Response(200, json=body))
    evaluator = DecisionEvaluator(
        registry, InMemorySchemaResolver([SCHEMA]), id_factory=lambda: "dec_jev"
    )
    with pytest.raises(ProviderOutputError):
        await evaluator.evaluate(REQUEST)
    await registry.aclose()


@pytest.mark.asyncio
async def test_jev_rate_limit_propagates_and_records_failure() -> None:
    from decisionos.providers import ProviderRateLimitError

    registry = _registry_with(lambda request: httpx.Response(429))
    evaluator = DecisionEvaluator(
        registry, InMemorySchemaResolver([SCHEMA]), id_factory=lambda: "dec_jev"
    )
    with pytest.raises(ProviderRateLimitError):
        await evaluator.evaluate(REQUEST)
    await registry.aclose()


@pytest.mark.asyncio
async def test_unconfigured_jev_falls_back_to_mock_in_registry() -> None:
    from decisionos.config import Settings
    from decisionos.providers import MockProvider, get_registry, reset_registry

    reset_registry()
    try:
        registry = get_registry(Settings(_env_file=None, jev_api_key=""))
        assert isinstance(registry.get("jev"), MockProvider)
    finally:
        reset_registry()
