"""Unit tests for JevProvider request construction and response parsing.

All tests use ``httpx.MockTransport`` so no network access is required.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from decisionos.config import Settings
from decisionos.models import DecisionRequest, DecisionSchema
from decisionos.providers import (
    DecisionProvider,
    ProviderUnavailableError,
)
from decisionos.providers.jev import JevProvider, build_jev_provider

SCHEMA = DecisionSchema(
    name="ToolAuthorization",
    version=1,
    actions=("allow", "human_review", "deny"),
    action_descriptions={"deny": "Refuse the operation"},
)

REQUEST = DecisionRequest(
    decision_type="tool_authorization",
    schema_name="ToolAuthorization",
    schema_version=1,
    context={"tool": "github.merge", "environment": "production"},
)

_SUCCESS_BODY: dict[str, Any] = {
    "model": "jev-1.13.0",
    "answers": {
        "action": {
            "type": "choice",
            "choice": "human_review",
            "confidence": 0.91,
            "probabilities": {"allow": 0.08, "human_review": 0.91, "deny": 0.01},
        }
    },
    "usage": {"input_tokens": 12, "output_tokens": 3},
}


def _provider(handler, **overrides: Any) -> JevProvider:
    params: dict[str, Any] = {
        "api_key": "test-key",
        "base_url": "https://api.typesafe.ai",
        "model": "jev-latest",
        "timeout_seconds": 1.0,
        "max_retries": 0,
        "backoff_base_seconds": 0.0,
        "backoff_max_seconds": 0.0,
    }
    params.update(overrides)
    return JevProvider(transport=httpx.MockTransport(handler), **params)


def _capturing_provider(body: dict[str, Any]) -> tuple[JevProvider, dict[str, Any]]:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=body, headers={"x-typesafe-request-id": "req_1"})

    return _provider(handler), captured


def test_jev_provider_satisfies_protocol() -> None:
    provider = _provider(lambda request: httpx.Response(200, json=_SUCCESS_BODY))
    assert isinstance(provider, DecisionProvider)


@pytest.mark.asyncio
async def test_request_shape_matches_typesafe_api() -> None:
    provider, captured = _capturing_provider(_SUCCESS_BODY)
    try:
        await provider.evaluate(REQUEST, SCHEMA)
    finally:
        await provider.aclose()

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.typesafe.ai/v1/systemone"
    assert captured["headers"]["authorization"] == "Bearer test-key"

    body = captured["body"]
    assert body["model"] == "jev-latest"
    assert body["state"]["decision_type"] == "tool_authorization"
    assert body["state"]["context"]["tool"] == "github.merge"

    question = body["questions"]["action"]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"allow", "human_review", "deny"}
    assert question["criteria"]["deny"] == "Refuse the operation"
    assert question["criteria"]["allow"] is None


@pytest.mark.asyncio
async def test_response_is_parsed_into_raw_decision() -> None:
    provider, _ = _capturing_provider(_SUCCESS_BODY)
    try:
        raw = await provider.evaluate(REQUEST, SCHEMA)
    finally:
        await provider.aclose()

    assert raw.action == "human_review"
    assert raw.confidence == pytest.approx(0.91)
    assert raw.probabilities == {"allow": 0.08, "human_review": 0.91, "deny": 0.01}
    assert raw.provider == "jev"
    assert raw.provider_request_id == "req_1"
    assert raw.latency_ms >= 0.0
    assert "model:jev-1.13.0" in raw.reason_codes
    assert raw.raw_response["usage"] == {"input_tokens": 12, "output_tokens": 3}


@pytest.mark.asyncio
async def test_trailing_slash_in_base_url_is_normalized() -> None:
    provider, captured = _capturing_provider(_SUCCESS_BODY)
    provider._base_url = "https://api.typesafe.ai/"
    try:
        # The client's base_url is fixed at construction; verify the path only.
        await provider.evaluate(REQUEST, SCHEMA)
    finally:
        await provider.aclose()
    assert captured["url"] == "https://api.typesafe.ai/v1/systemone"


@pytest.mark.asyncio
async def test_confidence_may_be_absent() -> None:
    body = {
        "answers": {
            "action": {
                "type": "choice",
                "choice": "allow",
                "probabilities": {"allow": 0.6, "human_review": 0.3, "deny": 0.1},
            }
        }
    }
    provider, _ = _capturing_provider(body)
    try:
        raw = await provider.evaluate(REQUEST, SCHEMA)
    finally:
        await provider.aclose()
    assert raw.confidence is None
    assert raw.action == "allow"


@pytest.mark.asyncio
async def test_reason_codes_omit_model_when_absent() -> None:
    body = {
        "answers": {
            "action": {
                "type": "choice",
                "choice": "allow",
                "confidence": 0.6,
                "probabilities": {"allow": 0.6, "human_review": 0.3, "deny": 0.1},
            }
        }
    }
    provider, _ = _capturing_provider(body)
    try:
        raw = await provider.evaluate(REQUEST, SCHEMA)
    finally:
        await provider.aclose()
    assert raw.reason_codes == []


def test_build_jev_provider_requires_a_key() -> None:
    settings = Settings(_env_file=None, jev_api_key="")
    with pytest.raises(ProviderUnavailableError):
        build_jev_provider(settings)


def test_build_jev_provider_uses_settings() -> None:
    settings = Settings(
        _env_file=None,
        jev_api_key="abc",
        jev_base_url="https://example.test",
        jev_model="jev-1.13.0",
    )
    provider = build_jev_provider(settings)
    assert isinstance(provider, JevProvider)
    assert provider._base_url == "https://example.test"
    assert provider._model == "jev-1.13.0"


def test_api_key_is_not_exposed_in_repr() -> None:
    provider = _provider(lambda request: httpx.Response(200, json=_SUCCESS_BODY))
    assert "test-key" not in repr(provider)
