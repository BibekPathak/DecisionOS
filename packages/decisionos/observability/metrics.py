"""Prometheus metrics for DecisionOS.

Phase 0 establishes the metric registry and a render function so ``/metrics``
is live. Instrumentation of the decision pipeline is added in Phase 8.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest
from prometheus_client import REGISTRY as DEFAULT_REGISTRY

# Use a dedicated registry so tests can inspect metrics deterministically and
# so the default process collectors do not pollute the endpoint.
REGISTRY = CollectorRegistry(auto_describe=True)

DECISIONS_TOTAL = Counter(
    "decisionos_decisions_total",
    "Total decisions processed, labelled by final action and provider.",
    labelnames=("action", "provider", "decision_type"),
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


def render_metrics() -> str:
    """Render the current metrics in Prometheus text exposition format."""
    return generate_latest(REGISTRY).decode("utf-8")


def content_type() -> str:
    """Return the Prometheus content type for ``/metrics`` responses."""
    return CONTENT_TYPE_LATEST


__all__ = [
    "DECISIONS_TOTAL",
    "DEFAULT_REGISTRY",
    "POLICY_OVERRIDES_TOTAL",
    "PROVIDER_ERRORS_TOTAL",
    "REGISTRY",
    "content_type",
    "render_metrics",
]
