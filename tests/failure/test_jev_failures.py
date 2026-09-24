"""Failure-path tests for JevProvider.

Simulates the failure modes required by the specification: timeout, HTTP 429,
HTTP 500/529, malformed responses, authentication failures, and network
failures, plus retry/backoff behaviour. No network access is used.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from decisionos.models import DecisionRequest, DecisionSchema
from decisionos.providers import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from decisionos.providers.jev import JevProvider

SCHEMA = DecisionSchema(name="S", version=1, actions=("allow", "deny"))
REQUEST = DecisionRequest(decision_type="t", schema_name="S", schema_version=1, context={"x": 1})
_SUCCESS = {
    "answers": {
        "action": {
            "type": "choice",
            "choice": "allow",
            "confidence": 0.9,
            "probabilities": {"allow": 0.9, "deny": 0.1},
        }
    }
}


def _provider(handler_or_transport, **overrides: Any) -> JevProvider:
    params: dict[str, Any] = {
        "api_key": "k",
        "base_url": "https://api.typesafe.ai",
        "model": "jev-latest",
        "timeout_seconds": 1.0,
        "max_retries": 0,
        "backoff_base_seconds": 0.0,
        "backoff_max_seconds": 0.0,
    }
    params.update(overrides)
    transport = (
        handler_or_transport
        if isinstance(handler_or_transport, httpx.AsyncBaseTransport)
        else httpx.MockTransport(handler_or_transport)
    )
    return JevProvider(transport=transport, **params)


def _status(status: int, headers: dict[str, str] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers or {})

    return handler


async def _expect(provider: JevProvider, exc_type: type[Exception]) -> Exception:
    try:
        await provider.evaluate(REQUEST, SCHEMA)
    except exc_type as error:
        return error
    finally:
        await provider.aclose()
    raise AssertionError(f"expected {exc_type.__name__} to be raised")


@pytest.mark.asyncio
async def test_401_is_auth_error_not_retryable() -> None:
    error = await _expect(_provider(_status(401)), ProviderAuthError)
    assert error.kind == "auth"
    assert error.retryable is False


@pytest.mark.asyncio
async def test_403_is_auth_error() -> None:
    error = await _expect(_provider(_status(403)), ProviderAuthError)
    assert error.kind == "auth"


@pytest.mark.asyncio
async def test_422_is_response_error_not_retryable() -> None:
    error = await _expect(_provider(_status(422)), ProviderResponseError)
    assert error.kind == "malformed_response"
    assert error.retryable is False


@pytest.mark.asyncio
async def test_429_is_rate_limit_error_with_retry_after() -> None:
    provider = _provider(_status(429, {"retry-after": "2.5"}))
    error = await _expect(provider, ProviderRateLimitError)
    assert error.kind == "rate_limit"
    assert error.retryable is True
    assert error.retry_after_seconds == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_500_is_unavailable_and_retryable() -> None:
    error = await _expect(_provider(_status(500)), ProviderUnavailableError)
    assert error.kind == "unavailable"
    assert error.retryable is True


@pytest.mark.asyncio
async def test_529_is_unavailable_and_retryable() -> None:
    error = await _expect(_provider(_status(529)), ProviderUnavailableError)
    assert error.retryable is True


@pytest.mark.asyncio
async def test_timeout_raises_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    error = await _expect(_provider(httpx.MockTransport(handler)), ProviderTimeoutError)
    assert error.kind == "timeout"
    assert error.retryable is True


@pytest.mark.asyncio
async def test_network_failure_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    error = await _expect(_provider(httpx.MockTransport(handler)), ProviderUnavailableError)
    assert error.kind == "unavailable"


@pytest.mark.asyncio
async def test_non_json_response_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>nope</html>")

    error = await _expect(_provider(httpx.MockTransport(handler)), ProviderResponseError)
    assert "non-JSON" in str(error)


@pytest.mark.asyncio
async def test_json_array_response_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    error = await _expect(_provider(httpx.MockTransport(handler)), ProviderResponseError)
    assert "JSON object" in str(error)


@pytest.mark.asyncio
async def test_missing_answers_is_rejected() -> None:
    error = await _expect(
        _provider(lambda request: httpx.Response(200, json={"model": "jev"})),
        ProviderResponseError,
    )
    assert "answers" in str(error)


@pytest.mark.asyncio
async def test_missing_action_answer_is_rejected() -> None:
    body = {"answers": {"other": {"type": "choice", "choice": "x"}}}
    error = await _expect(
        _provider(lambda request: httpx.Response(200, json=body)), ProviderResponseError
    )
    assert "action" in str(error)


@pytest.mark.asyncio
async def test_missing_choice_is_rejected() -> None:
    body = {"answers": {"action": {"type": "choice", "probabilities": {"allow": 0.5, "deny": 0.5}}}}
    error = await _expect(
        _provider(lambda request: httpx.Response(200, json=body)), ProviderResponseError
    )
    assert "choice" in str(error)


@pytest.mark.asyncio
async def test_missing_probabilities_is_rejected() -> None:
    body = {"answers": {"action": {"type": "choice", "choice": "allow", "confidence": 1.0}}}
    error = await _expect(
        _provider(lambda request: httpx.Response(200, json=body)), ProviderResponseError
    )
    assert "probabilities" in str(error)


@pytest.mark.asyncio
async def test_non_numeric_probability_is_rejected() -> None:
    body = {
        "answers": {
            "action": {
                "type": "choice",
                "choice": "allow",
                "probabilities": {"allow": "high", "deny": 0.1},
            }
        }
    }
    error = await _expect(
        _provider(lambda request: httpx.Response(200, json=body)), ProviderResponseError
    )
    assert "non-numeric" in str(error)


@pytest.mark.asyncio
async def test_error_includes_request_id_header() -> None:
    provider = _provider(_status(500, {"x-typesafe-request-id": "req_xyz"}))
    error = await _expect(provider, ProviderUnavailableError)
    assert error.request_id == "req_xyz"


@pytest.mark.asyncio
async def test_retries_then_succeeds_on_transient_errors() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=_SUCCESS)

    provider = _provider(httpx.MockTransport(handler), max_retries=3)
    raw = await provider.evaluate(REQUEST, SCHEMA)
    await provider.aclose()
    assert calls["n"] == 3
    assert raw.action == "allow"


@pytest.mark.asyncio
async def test_retries_are_exhausted_on_persistent_failure() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500)

    provider = _provider(httpx.MockTransport(handler), max_retries=2)
    await _expect(provider, ProviderUnavailableError)
    # one initial attempt plus two retries
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_auth_errors_are_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401)

    provider = _provider(httpx.MockTransport(handler), max_retries=3)
    await _expect(provider, ProviderAuthError)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_validation_errors_are_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(422)

    provider = _provider(httpx.MockTransport(handler), max_retries=3)
    await _expect(provider, ProviderResponseError)
    assert calls["n"] == 1
