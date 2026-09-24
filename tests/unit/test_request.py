"""Unit tests for DecisionRequest."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from decisionos.models import DEFAULT_MAX_CONTEXT_BYTES, DecisionRequest


def _request(**overrides: object) -> DecisionRequest:
    base: dict[str, object] = {
        "decision_type": "tool_authorization",
        "schema_name": "ToolAuthorization",
        "schema_version": 1,
        "context": {"tool": "github.merge"},
    }
    base.update(overrides)
    return DecisionRequest(**base)  # type: ignore[arg-type]


def test_minimal_request() -> None:
    request = _request()
    assert request.schema_key == "ToolAuthorization@1"
    assert request.context == {"tool": "github.merge"}
    assert request.metadata == {}
    assert request.provider is None
    assert request.policy is None
    assert request.idempotency_key is None


def test_schema_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _request(schema_version=0)


def test_blank_decision_type_rejected() -> None:
    with pytest.raises(ValidationError):
        _request(decision_type="  ")


def test_blank_idempotency_key_rejected() -> None:
    with pytest.raises(ValidationError):
        _request(idempotency_key="   ")


def test_idempotency_key_optional_and_preserved() -> None:
    request = _request(idempotency_key="abc-123")
    assert request.idempotency_key == "abc-123"


def test_context_size_within_default_limit() -> None:
    request = _request(context={"a": "b"})
    request.validate_context_size()
    assert request.context_size_bytes() > 0


def test_context_size_exceeds_default_limit() -> None:
    request = _request(context={"blob": "x" * (DEFAULT_MAX_CONTEXT_BYTES + 1)})
    with pytest.raises(ValueError, match="exceeding the limit"):
        request.validate_context_size()


def test_per_request_context_limit_override() -> None:
    request = _request(context={"blob": "x" * 100}, max_context_bytes=10)
    assert request.effective_max_context_bytes() == 10
    with pytest.raises(ValueError, match="exceeding the limit"):
        request.validate_context_size()


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        _request(unexpected="value")


def test_context_size_uses_compact_json() -> None:
    request = _request(context={"a": 1})
    # '{"a":1}' is 7 bytes.
    assert request.context_size_bytes() == 7
