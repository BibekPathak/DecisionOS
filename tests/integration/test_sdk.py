"""Integration tests for the Python SDK against the real API.

The SDK is bound to an ASGI transport so the full stack runs in-process:
SDK -> FastAPI -> engine -> mock provider -> policy -> PostgreSQL.
"""

from __future__ import annotations

import httpx
import pytest

from api.main import create_app
from decisionos.config import Settings
from decisionos.providers import reset_registry
from decisionos.sdk import AsyncDecisionOS
from decisionos.sdk.errors import NotFoundError
from decisionos.storage import Database, IdempotencyStore, InMemoryBackend, RateLimiter

from .conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.integration

SCHEMA = {
    "name": "ToolAuthorization",
    "actions": ["allow", "human_review", "deny"],
}
POLICY = {
    "name": "sdk-policy",
    "rules": [
        {
            "name": "production-merge",
            "when": {"environment": "production", "tool": "github.merge"},
            "action": {"require": "human_review"},
        }
    ],
}
CONTEXT = {
    "agent": "deploy-agent",
    "tool": "github.merge",
    "repository": "org/project",
    "environment": "production",
    "tests_passed": False,
}


@pytest.fixture()
async def sdk(engine):
    """An AsyncDecisionOS bound to the in-process app, sharing the test DB."""
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=TEST_DATABASE_URL,
        rate_limit_per_minute=10_000,
    )
    database = Database(settings)
    app = create_app(settings, database=database)
    async with app.router.lifespan_context(app):
        in_memory = InMemoryBackend()
        app.state.redis_backend = in_memory
        app.state.idempotency = IdempotencyStore(in_memory, ttl_seconds=3600)
        app.state.rate_limiter = RateLimiter(in_memory, limit=10_000)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http_client:
            yield AsyncDecisionOS("http://testserver", client=http_client)
    await database.dispose()
    reset_registry()


@pytest.mark.asyncio
async def test_health(sdk: AsyncDecisionOS) -> None:
    payload = await sdk.health()
    assert payload["status"] == "ok"


@pytest.mark.asyncio
async def test_decide_end_to_end(sdk: AsyncDecisionOS) -> None:
    await sdk.register_schema(**SCHEMA)
    await sdk.register_policy(**POLICY)
    decision = await sdk.decide(schema="ToolAuthorization", context=CONTEXT, policy="sdk-policy@1")
    assert decision.action == "human_review"
    assert decision.confidence == pytest.approx(0.91)
    assert decision.risk == pytest.approx(0.87)
    assert decision.provider == "mock"
    assert decision.policy is not None
    assert decision.policy.triggered_rules == ["production-merge"]


@pytest.mark.asyncio
async def test_decide_defaults_decision_type(sdk: AsyncDecisionOS) -> None:
    await sdk.register_schema(**SCHEMA)
    decision = await sdk.decide(schema="ToolAuthorization", context={"tool": "read_file"})
    assert decision.decision_type == "tool_authorization"


@pytest.mark.asyncio
async def test_get_and_list_decisions(sdk: AsyncDecisionOS) -> None:
    await sdk.register_schema(**SCHEMA)
    created = await sdk.decide(schema="ToolAuthorization", context={"tool": "read_file"})
    fetched = await sdk.get_decision(created.decision_id)
    assert fetched.decision_id == created.decision_id
    listing = await sdk.list_decisions()
    assert any(item.decision_id == created.decision_id for item in listing)


@pytest.mark.asyncio
async def test_explain(sdk: AsyncDecisionOS) -> None:
    await sdk.register_schema(**SCHEMA)
    created = await sdk.decide(schema="ToolAuthorization", context={"tool": "read_file"})
    explanation = await sdk.explain(created.decision_id)
    assert explanation.decision_id == created.decision_id
    assert explanation.provider == "mock"
    assert len(explanation.lifecycle) >= 3


@pytest.mark.asyncio
async def test_record_outcome(sdk: AsyncDecisionOS) -> None:
    await sdk.register_schema(**SCHEMA)
    created = await sdk.decide(schema="ToolAuthorization", context={"tool": "read_file"})
    outcome = await sdk.record_outcome(created.decision_id, actual_outcome="safe", success=True)
    assert outcome.success is True


@pytest.mark.asyncio
async def test_idempotency_key(sdk: AsyncDecisionOS) -> None:
    await sdk.register_schema(**SCHEMA)
    first = await sdk.decide(
        schema="ToolAuthorization", context=CONTEXT, idempotency_key="sdk-idem"
    )
    second = await sdk.decide(
        schema="ToolAuthorization", context=CONTEXT, idempotency_key="sdk-idem"
    )
    assert first.decision_id == second.decision_id


@pytest.mark.asyncio
async def test_list_schemas_and_policies(sdk: AsyncDecisionOS) -> None:
    await sdk.register_schema(**SCHEMA)
    await sdk.register_policy(**POLICY)
    assert any(s.name == "ToolAuthorization" for s in await sdk.list_schemas())
    assert any(p.name == "sdk-policy" for p in await sdk.list_policies())


@pytest.mark.asyncio
async def test_calibration_report(sdk: AsyncDecisionOS) -> None:
    await sdk.register_schema(**SCHEMA)
    created = await sdk.decide(schema="ToolAuthorization", context={"tool": "read_file"})
    await sdk.record_outcome(created.decision_id, actual_outcome="safe", success=True)
    report = await sdk.calibration(provider="mock")
    assert report.sample_count >= 1
    assert report.brier_score is not None


@pytest.mark.asyncio
async def test_not_found_raises_typed_error(sdk: AsyncDecisionOS) -> None:
    with pytest.raises(NotFoundError):
        await sdk.get_decision("dec_missing")
