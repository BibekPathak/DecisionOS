"""Prometheus metrics for DecisionOS.

A dedicated registry keeps the exposition deterministic and avoids polluting
``/metrics`` with default process collectors.

Metrics follow the names in the project specification:

* ``decisionos_decisions_total`` — counter
* ``decisionos_decision_latency_seconds`` — histogram
* ``decisionos_provider_latency_seconds`` — histogram
* ``decisionos_provider_errors_total`` — counter
* ``decisionos_policy_overrides_total`` — counter
* ``decisionos_calibration_error`` — gauge (set by the calibration report)

Histograms expose ``_bucket``/``_count``/``_sum`` series; percentile queries
(p50/p95/p99) are computed from the buckets by a query layer such as
Prometheus. A local helper for tests and CLIs is provided by
:func:`histogram_quantile`.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client import REGISTRY as DEFAULT_REGISTRY

REGISTRY = CollectorRegistry(auto_describe=True)

# Latency buckets in seconds. They are tuned for a decision runtime whose API
# responses are expected to be fast and whose provider calls may be slower.
_LATENCY_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

DECISIONS_TOTAL = Counter(
    "decisionos_decisions_total",
    "Total decisions processed, labelled by final action and provider.",
    labelnames=("action", "provider", "decision_type"),
    registry=REGISTRY,
)

DECISION_LATENCY = Histogram(
    "decisionos_decision_latency_seconds",
    "End-to-end decision evaluation latency, labelled by provider.",
    labelnames=("provider",),
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)

PROVIDER_LATENCY = Histogram(
    "decisionos_provider_latency_seconds",
    "Provider evaluation latency.",
    labelnames=("provider",),
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)

PROVIDER_ERRORS_TOTAL = Counter(
    "decisionos_provider_errors_total",
    "Total provider evaluation errors, labelled by provider and error kind.",
    labelnames=("provider", "error"),
    registry=REGISTRY,
)

POLICY_OVERRIDES_TOTAL = Counter(
    "decisionos_policy_overrides_total",
    "Decisions where deterministic policy overrode the model's suggested action.",
    labelnames=("policy", "final_action"),
    registry=REGISTRY,
)

HTTP_REQUEST_LATENCY = Histogram(
    "decisionos_http_request_latency_seconds",
    "HTTP request latency, labelled by method, route template, and status.",
    labelnames=("method", "route", "status"),
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)

CALIBRATION_ERROR = Gauge(
    "decisionos_calibration_error",
    "Most recently computed expected calibration error.",
    labelnames=("decision_type",),
    registry=REGISTRY,
)


def observe_decision(
    *,
    provider: str,
    action: str,
    decision_type: str,
    latency_seconds: float,
) -> None:
    """Record a completed decision."""
    DECISIONS_TOTAL.labels(action=action, provider=provider, decision_type=decision_type).inc()
    DECISION_LATENCY.labels(provider=provider).observe(max(latency_seconds, 0.0))


def observe_provider_latency(*, provider: str, latency_seconds: float) -> None:
    """Record a provider call's latency."""
    PROVIDER_LATENCY.labels(provider=provider).observe(max(latency_seconds, 0.0))


def record_provider_error(*, provider: str, kind: str) -> None:
    """Record a provider error by kind."""
    PROVIDER_ERRORS_TOTAL.labels(provider=provider, error=kind).inc()


def record_policy_override(*, policy: str, final_action: str) -> None:
    """Record a policy override of the model's action."""
    POLICY_OVERRIDES_TOTAL.labels(policy=policy, final_action=final_action).inc()


def observe_http_request(*, method: str, route: str, status: int, latency_seconds: float) -> None:
    """Record an HTTP request's latency."""
    HTTP_REQUEST_LATENCY.labels(method=method, route=route, status=str(status)).observe(
        max(latency_seconds, 0.0)
    )


def set_calibration_error(*, decision_type: str, value: float) -> None:
    """Set the latest expected calibration error for a decision type."""
    CALIBRATION_ERROR.labels(decision_type=decision_type).set(value)


def render_metrics() -> str:
    """Render the current metrics in Prometheus text exposition format."""
    return generate_latest(REGISTRY).decode("utf-8")


def content_type() -> str:
    """Return the Prometheus content type for ``/metrics`` responses."""
    return CONTENT_TYPE_LATEST


def histogram_quantile(metric_name: str, quantile: float, **label_filter: str) -> float | None:
    """Compute a quantile from a histogram's buckets in the local registry.

    Intended for tests, CLIs, and diagnostics. Returns ``None`` when the
    histogram has no observations. Production percentile queries are expected
    to use Prometheus' own ``histogram_quantile`` over these buckets.
    """
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")

    collector = REGISTRY._names_to_collectors.get(metric_name)
    if collector is None:
        return None

    # Aggregate bucket counts across matching label sets.
    buckets: dict[float, float] = {}
    total = 0.0
    for metric in collector.collect():
        for sample in metric.samples:
            if sample.name != f"{metric_name}_bucket":
                continue
            if not _matches(sample.labels, label_filter):
                continue
            le = sample.labels.get("le")
            if le is None:
                continue
            bound = float("inf") if le == "+Inf" else float(le)
            buckets[bound] = buckets.get(bound, 0.0) + sample.value
            if bound == float("inf"):
                total = sample.value if total == 0.0 else total

    if not buckets or total <= 0.0:
        return None

    ordered = sorted(buckets.items())
    rank = quantile * total
    for bound, cumulative in ordered:
        if cumulative >= rank:
            # Linear interpolation within the bucket using the previous bound.
            return bound
    return ordered[-1][0]


def _matches(labels: dict[str, str], label_filter: dict[str, str]) -> bool:
    return all(labels.get(key) == value for key, value in label_filter.items())


__all__ = [
    "CALIBRATION_ERROR",
    "DECISIONS_TOTAL",
    "DECISION_LATENCY",
    "DEFAULT_REGISTRY",
    "HTTP_REQUEST_LATENCY",
    "POLICY_OVERRIDES_TOTAL",
    "PROVIDER_ERRORS_TOTAL",
    "PROVIDER_LATENCY",
    "REGISTRY",
    "content_type",
    "histogram_quantile",
    "observe_decision",
    "observe_http_request",
    "observe_provider_latency",
    "record_policy_override",
    "record_provider_error",
    "render_metrics",
    "set_calibration_error",
]
