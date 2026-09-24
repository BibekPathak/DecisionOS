"""Phase 0 tests: secret redaction in structured logs."""

from __future__ import annotations

from typing import Any

from decisionos.observability.logging import redact_secrets

REDACTED = "***REDACTED***"


def _process(event: dict[str, Any]) -> dict[str, Any]:
    return dict(redact_secrets(None, "info", dict(event)))


def test_top_level_sensitive_keys_are_redacted() -> None:
    result = _process({"event": "x", "api_key": "abc", "authorization": "Bearer z"})
    assert result["api_key"] == REDACTED
    assert result["authorization"] == REDACTED
    assert result["event"] == "x"


def test_nested_mappings_are_redacted() -> None:
    result = _process({"event": "x", "ctx": {"token": "abc", "safe": "ok"}})
    assert result["ctx"]["token"] == REDACTED
    assert result["ctx"]["safe"] == "ok"


def test_lists_are_redacted() -> None:
    result = _process({"event": "x", "items": [{"secret": "a"}, {"ok": 1}]})
    assert result["items"][0]["secret"] == REDACTED
    assert result["items"][1]["ok"] == 1


def test_sensitive_substrings_are_redacted() -> None:
    result = _process({"event": "x", "note": "Bearer sk-abcdef", "plain": "hello"})
    assert result["note"] == REDACTED
    assert result["plain"] == "hello"


def test_key_matching_is_case_insensitive() -> None:
    result = _process({"event": "x", "API_KEY": "abc"})
    assert result["API_KEY"] == REDACTED
