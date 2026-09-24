"""Unit tests for the provider abstraction and its exceptions."""

from __future__ import annotations

import pytest

from decisionos.models import DecisionRequest, DecisionSchema, RawDecision
from decisionos.providers import (
    DecisionProvider,
    MockProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


def test_mock_provider_satisfies_protocol() -> None:
    assert isinstance(MockProvider(), DecisionProvider)


def test_provider_error_carries_provider_and_request_id() -> None:
    error = ProviderError("boom", provider="jev", request_id="req_1")
    assert error.provider == "jev"
    assert error.request_id == "req_1"


def test_error_kinds_are_distinct() -> None:
    assert ProviderUnavailableError.kind == "unavailable"
    assert ProviderTimeoutError.kind == "timeout"
    assert ProviderRateLimitError.kind == "rate_limit"
    assert ProviderAuthError.kind == "auth"
    assert ProviderResponseError.kind == "malformed_response"


def test_retryable_flags() -> None:
    assert ProviderUnavailableError.retryable is True
    assert ProviderTimeoutError.retryable is True
    assert ProviderRateLimitError.retryable is True
    assert ProviderAuthError.retryable is False
    assert ProviderResponseError.retryable is False


def test_rate_limit_error_carries_retry_after() -> None:
    error = ProviderRateLimitError("slow down", provider="jev", retry_after_seconds=1.5)
    assert error.retry_after_seconds == 1.5


def test_errors_are_provider_errors() -> None:
    for cls in (
        ProviderUnavailableError,
        ProviderTimeoutError,
        ProviderRateLimitError,
        ProviderAuthError,
        ProviderResponseError,
    ):
        assert issubclass(cls, ProviderError)


@pytest.mark.asyncio
async def test_custom_provider_satisfies_protocol() -> None:
    class StubProvider:
        name = "stub"

        async def evaluate(self, request: DecisionRequest, schema: DecisionSchema) -> RawDecision:
            return RawDecision(
                action=schema.actions[0],
                probabilities={schema.actions[0]: 1.0},
                confidence=1.0,
                provider=self.name,
                latency_ms=0.0,
            )

    provider: DecisionProvider = StubProvider()
    schema = DecisionSchema(name="S", version=1, actions=("allow",))
    request = DecisionRequest(decision_type="t", schema_name="S", schema_version=1, context={})
    raw = await provider.evaluate(request, schema)
    assert raw.action == "allow"
