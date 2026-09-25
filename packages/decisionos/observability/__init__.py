"""Observability primitives: logging, tracing, metrics, and request context."""

from __future__ import annotations

from decisionos.observability.context import (
    RequestContext,
    get_request_context,
    request_context,
)
from decisionos.observability.logging import configure_logging, get_logger
from decisionos.observability.metrics import (
    observe_decision,
    observe_http_request,
    observe_provider_latency,
    record_policy_override,
    record_provider_error,
    render_metrics,
)
from decisionos.observability.tracing import (
    configure_tracing,
    current_trace_id,
    get_tracer,
    shutdown_tracing,
    span,
)

__all__ = [
    "RequestContext",
    "configure_logging",
    "configure_tracing",
    "current_trace_id",
    "get_logger",
    "get_request_context",
    "get_tracer",
    "observe_decision",
    "observe_http_request",
    "observe_provider_latency",
    "record_policy_override",
    "record_provider_error",
    "render_metrics",
    "request_context",
    "shutdown_tracing",
    "span",
]
