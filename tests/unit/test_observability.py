"""Unit tests for observability: context, logging, metrics, and tracing."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
import structlog

from decisionos.observability.context import (
    RequestContext,
    get_request_context,
    request_context,
    set_request_context,
)
from decisionos.observability.metrics import (
    histogram_quantile,
    observe_decision,
    observe_http_request,
    observe_provider_latency,
    record_policy_override,
    record_provider_error,
    render_metrics,
    set_calibration_error,
)
from decisionos.observability.tracing import (
    configure_tracing,
    get_tracer,
    shutdown_tracing,
    span,
)

# --- request context --------------------------------------------------------


def test_request_context_defaults_to_empty() -> None:
    assert get_request_context().log_fields() == {}


def test_request_context_manager_enriches_and_resets() -> None:
    with request_context(request_id="req_1"):
        assert get_request_context().request_id == "req_1"
        with request_context(decision_id="dec_1"):
            context = get_request_context()
            # Nested updates preserve existing fields.
            assert context.request_id == "req_1"
            assert context.decision_id == "dec_1"
        assert get_request_context().decision_id is None
    assert get_request_context().request_id is None


def test_request_context_none_values_are_ignored() -> None:
    with request_context(request_id="req_1"), request_context(provider=None, schema="S@1"):
        context = get_request_context()
        assert context.request_id == "req_1"
        assert context.schema == "S@1"


def test_trace_attributes_omit_empty_fields() -> None:
    context = RequestContext(request_id="r", provider="mock")
    attributes = context.trace_attributes()
    assert attributes["decisionos.request_id"] == "r"
    assert attributes["decisionos.provider"] == "mock"
    assert "decisionos.decision_id" not in attributes


def test_set_and_reset_context() -> None:
    token = set_request_context(RequestContext(request_id="x"))
    assert get_request_context().request_id == "x"
    from decisionos.observability.context import reset_request_context

    reset_request_context(token)
    assert get_request_context().request_id is None


# --- logging ----------------------------------------------------------------


@pytest.fixture()
def _restore_logging() -> Any:
    """Reset structlog configuration after a test that reconfigures it."""
    import structlog

    yield
    structlog.reset_defaults()


def _capture_logs() -> Any:
    buffer: list[str] = []

    class _Writer:
        def write(self, message: str) -> None:
            for line in message.splitlines():
                if line.strip():
                    buffer.append(line)

        def flush(self) -> None:  # pragma: no cover
            pass

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            __import__(
                "decisionos.observability.logging", fromlist=["_merge_request_context"]
            )._merge_request_context,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(_Writer()),
        cache_logger_on_first_use=False,
    )
    return buffer


def test_logs_include_request_context(_restore_logging: Any) -> None:
    buffer = _capture_logs()
    logger = structlog.get_logger("test")
    with request_context(request_id="req_9", decision_id="dec_9"):
        logger.info("hello", extra_field="v")
    record = json.loads(buffer[-1])
    assert record["request_id"] == "req_9"
    assert record["decision_id"] == "dec_9"
    assert record["extra_field"] == "v"
    assert record["event"] == "hello"


def test_explicit_log_field_overrides_context(_restore_logging: Any) -> None:
    buffer = _capture_logs()
    logger = structlog.get_logger("test")
    with request_context(request_id="req_ctx"):
        logger.info("hello", request_id="req_explicit")
    record = json.loads(buffer[-1])
    assert record["request_id"] == "req_explicit"


# --- metrics ----------------------------------------------------------------


def test_render_metrics_contains_expected_names() -> None:
    text = render_metrics()
    for name in (
        "decisionos_decisions_total",
        "decisionos_decision_latency_seconds",
        "decisionos_provider_latency_seconds",
        "decisionos_provider_errors_total",
        "decisionos_policy_overrides_total",
        "decisionos_calibration_error",
        "decisionos_http_request_latency_seconds",
    ):
        assert name in text


def test_observe_decision_records_counter_and_latency() -> None:
    observe_decision(
        provider="test-provider",
        action="allow",
        decision_type="unit_test",
        latency_seconds=0.012,
    )
    text = render_metrics()
    assert 'decisionos_decisions_total{action="allow"' in text
    assert 'provider="test-provider"' in text
    assert 'decision_type="unit_test"' in text


def test_observe_provider_latency_and_errors() -> None:
    observe_provider_latency(provider="test-provider", latency_seconds=0.05)
    record_provider_error(provider="test-provider", kind="timeout")
    text = render_metrics()
    assert 'decisionos_provider_latency_seconds_count{provider="test-provider"}' in text
    assert 'decisionos_provider_errors_total{error="timeout",provider="test-provider"}' in text


def test_record_policy_override() -> None:
    record_policy_override(policy="test-policy", final_action="deny")
    text = render_metrics()
    assert 'decisionos_policy_overrides_total{final_action="deny",policy="test-policy"}' in text


def test_set_calibration_error() -> None:
    set_calibration_error(decision_type="unit_test", value=0.041)
    text = render_metrics()
    assert 'decisionos_calibration_error{decision_type="unit_test"} 0.041' in text


def test_observe_http_request() -> None:
    observe_http_request(
        method="GET", route="/v1/decisions/{id}", status=200, latency_seconds=0.003
    )
    text = render_metrics()
    assert "decisionos_http_request_latency_seconds_count" in text
    assert 'route="/v1/decisions/{id}"' in text


def test_histogram_quantile_rejects_bad_quantile() -> None:
    with pytest.raises(ValueError):
        histogram_quantile("decisionos_decision_latency_seconds", 1.5)


def test_histogram_quantile_unknown_metric_returns_none() -> None:
    assert histogram_quantile("does_not_exist", 0.5) is None


def test_histogram_quantile_locally_estimates() -> None:
    for _ in range(10):
        observe_decision(
            provider="quantile-provider",
            action="allow",
            decision_type="q",
            latency_seconds=0.02,
        )
    value = histogram_quantile(
        "decisionos_decision_latency_seconds", 0.95, provider="quantile-provider"
    )
    assert value is not None
    assert 0.0 < value <= 10.0


# --- tracing ----------------------------------------------------------------


def test_tracer_can_create_spans() -> None:
    configure_tracing(force=True)
    tracer = get_tracer()
    with tracer.start_as_current_span("unit") as current:
        current.set_attribute("k", "v")
        assert current.is_recording()
    shutdown_tracing()


def test_span_helper_attaches_request_context() -> None:
    configure_tracing(force=True)
    with (
        request_context(request_id="req_span", decision_id="dec_span"),
        span("unit.span", custom="value") as current,
    ):
        assert current.is_recording()
        assert current.attributes is not None
    shutdown_tracing()


def test_span_omits_none_attributes() -> None:
    configure_tracing(force=True)
    with span("unit.span", present="x", absent=None) as current:
        attributes = dict(current.attributes or {})
        assert "present" in attributes
        assert "absent" not in attributes
    shutdown_tracing()
