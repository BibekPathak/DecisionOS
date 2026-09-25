"""Structured JSON logging for DecisionOS with secret redaction.

All logs are emitted as JSON. A redaction processor removes values that are
known to be secret (API keys, authorization headers, configured sensitive
keys) before records are rendered, so secrets and authorization material can
never reach a log sink.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, MutableMapping
from typing import Any

import structlog

# Keys whose values must never appear in logs. Matching is case-insensitive and
# applies to nested mappings as well as top-level event dictionaries.
_REDACTED = "***REDACTED***"
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "jev_api_key",
        "typesafe_api_key",
        "x-api-key",
    }
)

# A small set of substrings that, when found in a string value, indicate a
# bearer credential. Guards against secrets smuggled inside free-form strings.
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = ("bearer ", "sk-", "ts_")


def _redact_value(value: Any) -> Any:
    if isinstance(value, MutableMapping):
        return _redact_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(sub in lowered for sub in _SENSITIVE_SUBSTRINGS):
            return _REDACTED
    return value


def _redact_mapping(mapping: MutableMapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
            redacted[key] = _REDACTED
        else:
            redacted[key] = _redact_value(value)
    return redacted


def redact_secrets(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor that redacts sensitive values from a log record."""
    return _redact_mapping(event_dict)


def _add_log_level(
    _logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    event_dict.setdefault("level", method_name)
    return event_dict


def _merge_request_context(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Attach the active request identifiers to every log record.

    Explicit event fields win over context defaults so a caller may override a
    value for a single record.
    """
    from decisionos.observability.context import get_request_context

    for key, value in get_request_context().log_fields().items():
        event_dict.setdefault(key, value)
    return event_dict


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    """Configure stdlib logging and structlog for JSON output.

    Parameters
    ----------
    level:
        Root log level name, e.g. ``"INFO"`` or ``"DEBUG"``.
    json_logs:
        When ``True`` (default) render JSON. When ``False`` render a
        human-friendly console output (useful in tests).
    """
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    logging.basicConfig(
        format="%(message)s",
        level=numeric_level,
        force=True,
    )

    shared_processors: Iterable[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        _add_log_level,
        _merge_request_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_secrets,
    ]

    renderer: Any
    if json_logs:
        renderer = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
