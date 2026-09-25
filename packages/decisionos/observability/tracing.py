"""OpenTelemetry tracing setup and helpers.

Tracing is opt-in: when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset, a provider
with no exporter is installed and spans are still created (so instrumentation
code is uniform) but nothing is exported. When an endpoint is configured, spans
are exported over OTLP/HTTP and sampled at ``TRACE_SAMPLE_RATIO``.

The module exposes a :func:`get_tracer` helper and a :func:`span` context
manager that attaches decision-related attributes without leaking sensitive
context.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from decisionos.config import Settings, get_settings
from decisionos.observability.context import get_request_context

_TRACER_NAME = "decisionos"

_provider: Any = None
_configured = False


def configure_tracing(settings: Settings | None = None, *, force: bool = False) -> Any:
    """Configure the global tracer provider once.

    Returns the provider. Safe to call multiple times; only the first call (or a
    forced call) reconfigures.
    """
    global _provider, _configured
    if _configured and not force:
        return _provider

    settings = settings or get_settings()
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.trace_sample_ratio)),
    )

    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )

    trace.set_tracer_provider(provider)
    _provider = provider
    _configured = True
    return provider


def get_tracer() -> Any:
    """Return the DecisionOS tracer (configured lazily)."""
    if not _configured:
        configure_tracing()
    from opentelemetry import trace

    return trace.get_tracer(_TRACER_NAME)


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider, if one was configured."""
    global _provider, _configured
    if _provider is not None:
        _provider.shutdown()
    _provider = None
    _configured = False


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Start a span, attaching the current request context and attributes.

    ``None`` attributes are omitted. Values must be primitive span attribute
    types; nothing from the decision context is attached beyond what callers
    pass explicitly.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as current:
        context = get_request_context()
        for key, value in context.trace_attributes().items():
            current.set_attribute(key, value)
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def current_trace_id() -> str | None:
    """Return the current trace id as a hex string, if any."""
    from opentelemetry import trace

    span_context = trace.get_current_span().get_span_context()
    if not span_context or not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


__all__ = [
    "configure_tracing",
    "current_trace_id",
    "get_tracer",
    "shutdown_tracing",
    "span",
]
