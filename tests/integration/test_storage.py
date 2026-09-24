"""Integration tests for the persistence layer against PostgreSQL."""

from __future__ import annotations

import asyncio

import pytest

from decisionos.engine.lifecycle import DecisionLifecycle
from decisionos.models import (
    Decision,
    DecisionSchema,
    Outcome,
    Policy,
)
from decisionos.storage import (
    Cache,
    DecisionFilter,
    DecisionRecord,
    DecisionRepository,
    DecisionSchemaRepository,
    IdempotencyStore,
    InMemoryBackend,
    PolicyRepository,
    RateLimiter,
)

pytestmark = pytest.mark.integration

TOOL_SCHEMA = DecisionSchema(
    name="ToolAuthorization",
    version=1,
    actions=("allow", "human_review", "deny"),
)
POLICY = Policy(
    name="production-agent-policy",
    version=1,
    rules=({"name": "high-risk", "when": {"risk": {"gt": 0.9}}, "action": {"require": "deny"}},),
)


def _decision(decision_id: str, *, action: str = "allow", risk: float = 0.95) -> Decision:
    return Decision(
        id=decision_id,
        decision_type="tool_authorization",
        schema_name="ToolAuthorization",
        schema_version=1,
        action=action,
        confidence=0.97,
        probabilities={"allow": 0.97, "human_review": 0.0, "deny": 0.03},
        risk=risk,
        reason_codes=["seed"],
        provider="mock",
        latency_ms=5.0,
    )


@pytest.mark.asyncio
async def test_schema_repository_roundtrip(session) -> None:
    repo = DecisionSchemaRepository(session)
    await repo.add(TOOL_SCHEMA)
    loaded = await repo.get("ToolAuthorization", 1)
    assert loaded.actions == TOOL_SCHEMA.actions
    assert await repo.resolve("ToolAuthorization", 1) == TOOL_SCHEMA


@pytest.mark.asyncio
async def test_schema_repository_is_idempotent_but_rejects_conflict(session) -> None:
    repo = DecisionSchemaRepository(session)
    await repo.add(TOOL_SCHEMA)
    await repo.add(TOOL_SCHEMA)
    conflicting = DecisionSchema(name="ToolAuthorization", version=1, actions=("allow", "deny"))
    with pytest.raises(ValueError, match="different content"):
        await repo.add(conflicting)


@pytest.mark.asyncio
async def test_schema_repository_latest(session) -> None:
    repo = DecisionSchemaRepository(session)
    await repo.add(DecisionSchema(name="S", version=1, actions=("a",)))
    await repo.add(DecisionSchema(name="S", version=2, actions=("a", "b")))
    assert (await repo.latest("S")).version == 2
    assert [s.version for s in await repo.list_all()] == [1, 2]


@pytest.mark.asyncio
async def test_policy_repository_roundtrip(session) -> None:
    repo = PolicyRepository(session)
    await repo.add(POLICY)
    loaded = await repo.get("production-agent-policy", 1)
    assert loaded == POLICY
    assert (await repo.get_by_key("production-agent-policy@1")).version == 1
    assert (await repo.get("production-agent-policy")).version == 1


@pytest.mark.asyncio
async def test_policy_repository_rejects_conflict(session) -> None:
    repo = PolicyRepository(session)
    await repo.add(POLICY)
    conflicting = Policy(
        name="production-agent-policy",
        version=1,
        rules=({"name": "other", "when": {"x": 1}, "action": {"require": "deny"}},),
    )
    with pytest.raises(ValueError, match="different content"):
        await repo.add(conflicting)


@pytest.mark.asyncio
async def test_decision_save_and_fetch(session) -> None:
    repo = DecisionRepository(session)
    decision = _decision("dec_1")
    lifecycle = DecisionLifecycle("dec_1")
    lifecycle.start_evaluation()
    lifecycle.complete_evaluation()
    await repo.save(
        DecisionRecord(
            decision=decision,
            decision_type="tool_authorization",
            model_action="allow",
            context={"tool": "read_file"},
            idempotency_key="idem-1",
            events=list(lifecycle.events),
            policy_name="production-agent-policy",
            policy_version=1,
            policy_overridden=True,
            policy_precedence="hard_deny",
            triggered_rules=["high-risk"],
        )
    )
    loaded = await repo.get("dec_1")
    assert loaded is not None
    assert loaded.action == "allow"
    assert loaded.probabilities["allow"] == pytest.approx(0.97)
    assert await repo.get("missing") is None


@pytest.mark.asyncio
async def test_decision_events_are_persisted_in_order(session) -> None:
    repo = DecisionRepository(session)
    lifecycle = DecisionLifecycle("dec_events")
    lifecycle.start_evaluation()
    lifecycle.complete_evaluation()
    await repo.save(
        DecisionRecord(
            decision=_decision("dec_events"),
            decision_type="tool_authorization",
            model_action="allow",
            events=list(lifecycle.events),
        )
    )
    events = await repo.get_events("dec_events")
    assert [e.type.value for e in events] == [
        "created",
        "evaluation_started",
        "evaluation_completed",
    ]


@pytest.mark.asyncio
async def test_decision_idempotency_lookup(session) -> None:
    repo = DecisionRepository(session)
    await repo.save(
        DecisionRecord(
            decision=_decision("dec_idem"),
            decision_type="tool_authorization",
            model_action="allow",
            idempotency_key="abc",
        )
    )
    found = await repo.get_by_idempotency_key("abc")
    assert found is not None and found.id == "dec_idem"
    assert await repo.get_by_idempotency_key("nope") is None


@pytest.mark.asyncio
async def test_decision_listing_and_filters(session) -> None:
    repo = DecisionRepository(session)
    for index in range(3):
        await repo.save(
            DecisionRecord(
                decision=_decision(f"dec_{index}", action="allow" if index < 2 else "deny"),
                decision_type="tool_authorization",
                model_action="allow",
                context={"i": index},
            )
        )
    assert await repo.count() == 3
    assert await repo.count(DecisionFilter(action="allow")) == 2
    assert len(await repo.list(DecisionFilter(action="deny"))) == 1
    assert len(await repo.list(DecisionFilter(limit=2))) == 2


@pytest.mark.asyncio
async def test_outcome_recording_advances_state(session) -> None:
    repo = DecisionRepository(session)
    await repo.save(
        DecisionRecord(
            decision=_decision("dec_out"),
            decision_type="tool_authorization",
            model_action="allow",
        )
    )
    await repo.record_outcome(Outcome(decision_id="dec_out", actual_outcome="safe", success=True))
    outcome = await repo.get_outcome("dec_out")
    assert outcome is not None and outcome.success is True
    assert len(await repo.list_outcomes()) == 1


@pytest.mark.asyncio
async def test_decision_delete_cascades(session) -> None:
    from sqlalchemy import text

    repo = DecisionRepository(session)
    lifecycle = DecisionLifecycle("dec_cascade")
    lifecycle.start_evaluation()
    await repo.save(
        DecisionRecord(
            decision=_decision("dec_cascade"),
            decision_type="tool_authorization",
            model_action="allow",
            events=list(lifecycle.events),
        )
    )
    await session.execute(text("DELETE FROM decisions WHERE id = 'dec_cascade'"))
    await session.flush()
    assert await repo.get_events("dec_cascade") == []


# --- Redis-backed coordination (in-memory backend) -------------------------


@pytest.mark.asyncio
async def test_idempotency_reservation_is_exclusive() -> None:
    store = IdempotencyStore(InMemoryBackend())
    assert await store.reserve("k") is True
    assert await store.reserve("k") is False
    await store.complete("k", "dec_1")
    assert await store.get("k") == "dec_1"


@pytest.mark.asyncio
async def test_idempotency_release_allows_retry() -> None:
    store = IdempotencyStore(InMemoryBackend())
    await store.reserve("k")
    await store.release("k")
    assert await store.reserve("k") is True


@pytest.mark.asyncio
async def test_concurrent_duplicate_requests_single_winner() -> None:
    store = IdempotencyStore(InMemoryBackend())

    async def attempt() -> bool:
        return await store.reserve("race")

    results = await asyncio.gather(*(attempt() for _ in range(20)))
    assert sum(1 for won in results if won) == 1


@pytest.mark.asyncio
async def test_rate_limiter_allows_then_blocks() -> None:
    limiter = RateLimiter(InMemoryBackend(), limit=3, window_seconds=60)
    assert (await limiter.check("client")).allowed is True
    assert (await limiter.check("client")).allowed is True
    assert (await limiter.check("client")).allowed is True
    blocked = await limiter.check("client")
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 60
    # A different identifier has its own window.
    assert (await limiter.check("other")).allowed is True


@pytest.mark.asyncio
async def test_cache_roundtrip() -> None:
    cache = Cache(InMemoryBackend())
    assert await cache.get_json("k") is None
    await cache.set_json("k", {"a": 1})
    assert await cache.get_json("k") == {"a": 1}
