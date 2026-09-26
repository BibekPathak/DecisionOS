"""Unit tests for the SDK clients using a mock HTTP transport.

These exercise request construction, response parsing, and error mapping
without a running server.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from decisionos.sdk import AsyncDecisionOS, DecisionOS
from decisionos.sdk.errors import (
    AuthenticationError,
    BadRequestError,
    DecisionOSConnectionError,
    NotFoundError,
    RateLimitError,
    ServerError,
)

_DECISION = {
    "decision_id": "dec_1",
    "decision_type": "tool_authorization",
    "schema_name": "ToolAuthorization",
    "schema_version": 1,
    "action": "human_review",
    "model_action": "human_review",
    "confidence": 0.91,
    "probabilities": {"allow": 0.08, "human_review": 0.91, "deny": 0.01},
    "risk": 0.87,
    "reason_codes": ["production_repository"],
    "provider": "mock",
    "provider_request_id": "req_1",
    "latency_ms": 84.0,
    "created_at": "2026-01-01T00:00:00Z",
}


def _sync_client(handler) -> DecisionOS:
    return DecisionOS(
        "http://testserver",
        client=httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(handler)),
    )


def _async_client(handler) -> AsyncDecisionOS:
    return AsyncDecisionOS(
        "http://testserver",
        client=httpx.AsyncClient(
            base_url="http://testserver", transport=httpx.MockTransport(handler)
        ),
    )


# --- synchronous client -----------------------------------------------------


def test_sync_decide_request_and_parse() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=_DECISION)

    client = _sync_client(handler)
    decision = client.decide(
        schema="ToolAuthorization",
        context={"tool": "github.merge"},
        idempotency_key="k1",
    )
    assert decision.action == "human_review"
    assert captured["url"].endswith("/v1/decisions")
    assert captured["body"]["schema_name"] == "ToolAuthorization"
    assert captured["body"]["decision_type"] == "tool_authorization"
    assert captured["body"]["context"] == {"tool": "github.merge"}


def test_sync_not_found_raises() -> None:
    client = _sync_client(lambda request: httpx.Response(404, json={"detail": "nope"}))
    with pytest.raises(NotFoundError) as excinfo:
        client.get_decision("dec_missing")
    assert excinfo.value.status_code == 404


def test_sync_authentication_error() -> None:
    client = _sync_client(lambda request: httpx.Response(401, json={"detail": "bad key"}))
    with pytest.raises(AuthenticationError):
        client.health()


def test_sync_bad_request_error() -> None:
    client = _sync_client(lambda request: httpx.Response(422, json={"detail": "invalid"}))
    with pytest.raises(BadRequestError):
        client.decide(schema="S", context={})


def test_sync_server_error() -> None:
    client = _sync_client(lambda request: httpx.Response(500, json={"detail": "boom"}))
    with pytest.raises(ServerError):
        client.health()


def test_sync_rate_limit_error_carries_retry_after() -> None:
    client = _sync_client(
        lambda request: httpx.Response(429, headers={"retry-after": "3"}, json={})
    )
    with pytest.raises(RateLimitError) as excinfo:
        client.health()
    assert excinfo.value.retry_after == pytest.approx(3.0)


def test_sync_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = _sync_client(handler)
    with pytest.raises(DecisionOSConnectionError):
        client.health()


def test_sync_error_keeps_request_id() -> None:
    client = _sync_client(
        lambda request: httpx.Response(
            500, headers={"x-request-id": "req_9"}, json={"detail": "boom"}
        )
    )
    with pytest.raises(ServerError) as excinfo:
        client.health()
    assert excinfo.value.request_id == "req_9"


def test_sync_list_decisions_params() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[_DECISION])

    client = _sync_client(handler)
    rows = client.list_decisions(provider="mock", limit=5)
    assert len(rows) == 1
    assert captured["params"] == {"limit": "5", "offset": "0", "provider": "mock"}


def test_sync_record_outcome() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "decision_id": "dec_1",
                "actual_outcome": "safe",
                "success": True,
                "metadata": {},
                "recorded_at": "2026-01-01T00:00:00Z",
            },
        )

    client = _sync_client(handler)
    outcome = client.record_outcome("dec_1", actual_outcome="safe", success=True)
    assert outcome.success is True


def test_sync_calibration() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "sample_count": 2,
                "brier_score": 0.1,
                "expected_calibration_error": 0.05,
                "buckets": [],
            },
        )

    client = _sync_client(handler)
    report = client.calibration()
    assert report.sample_count == 2


# --- asynchronous client ----------------------------------------------------


@pytest.mark.asyncio
async def test_async_decide() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_DECISION)

    client = _async_client(handler)
    try:
        decision = await client.decide(schema="ToolAuthorization", context={})
        assert decision.action == "human_review"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_async_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "missing"})

    client = _async_client(handler)
    try:
        with pytest.raises(NotFoundError):
            await client.get_decision("nope")
    finally:
        await client.aclose()
