"""Request-scoped context propagated across logs, spans, and metrics.

A small set of identifiers (request id, decision id, provider, schema, policy
version) travels with a request. They are stored in :mod:`contextvars` so every
log line and span can attach them without threading parameters through every
function.

Only identifiers belong here. Decision *context* (which may be sensitive) is
never stored in this structure.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class RequestContext:
    """Identifiers associated with the current request or decision."""

    request_id: str | None = None
    trace_id: str | None = None
    decision_id: str | None = None
    provider: str | None = None
    schema: str | None = None
    policy_version: str | None = None

    def trace_attributes(self) -> dict[str, Any]:
        """Return non-null fields as span attributes."""
        attributes: dict[str, Any] = {}
        if self.request_id:
            attributes["decisionos.request_id"] = self.request_id
        if self.decision_id:
            attributes["decisionos.decision_id"] = self.decision_id
        if self.provider:
            attributes["decisionos.provider"] = self.provider
        if self.schema:
            attributes["decisionos.schema"] = self.schema
        if self.policy_version:
            attributes["decisionos.policy_version"] = self.policy_version
        return attributes

    def log_fields(self) -> dict[str, Any]:
        """Return non-null fields for structured logging."""
        return {key: value for key, value in self.__dict__.items() if value is not None}


_current: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "decisionos_request_context", default=None
)


def get_request_context() -> RequestContext:
    """Return the current request context, or an empty one if unset."""
    context = _current.get()
    return context if context is not None else RequestContext()


def set_request_context(context: RequestContext) -> contextvars.Token[RequestContext | None]:
    """Replace the current request context, returning a reset token."""
    return _current.set(context)


def reset_request_context(token: contextvars.Token[RequestContext | None]) -> None:
    """Restore the context to the value before a :func:`set_request_context`."""
    _current.reset(token)


class request_context:
    """Context manager that updates the request context for a block.

    Fields left as ``None`` are preserved from the active context, so callers
    can enrich the context incrementally (e.g. add a provider inside the
    evaluator without clearing the request id).
    """

    def __init__(self, **fields: Any) -> None:
        self._fields = fields
        self._token: contextvars.Token[RequestContext | None] | None = None

    def __enter__(self) -> RequestContext:
        updated = replace(
            get_request_context(),
            **{key: value for key, value in self._fields.items() if value is not None},
        )
        self._token = set_request_context(updated)
        return updated

    def __exit__(self, *_exc: object) -> None:
        if self._token is not None:
            reset_request_context(self._token)
            self._token = None


__all__ = [
    "RequestContext",
    "get_request_context",
    "request_context",
    "reset_request_context",
    "set_request_context",
]
