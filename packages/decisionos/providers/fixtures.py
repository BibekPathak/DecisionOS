"""Deterministic fixtures for :class:`MockProvider`.

Fixtures map a *context signature* — a small set of salient context fields —
to a fixed probability distribution. Lookups are deterministic: the same
request always yields the same output, so tests, demos, and the dashboard
render stable data without any external credentials.

The flagship AgentGuard fixture reproduces the distribution used throughout the
project specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MockFixture:
    """A deterministic provider response.

    Attributes
    ----------
    action:
        The action the mock selects.
    probabilities:
        Distribution over the schema's actions.
    confidence:
        Confidence in ``action``.
    risk:
        Optional risk estimate. When ``None`` DecisionOS derives it.
    reason_codes:
        Reason codes explaining the selection.
    match:
        Field/value pairs that must all be present in the context for this
        fixture to apply. An empty mapping matches any context.
    schema_name:
        Optional schema the fixture is scoped to.
    """

    action: str
    probabilities: dict[str, float]
    confidence: float
    risk: float | None = None
    reason_codes: list[str] = field(default_factory=list)
    match: dict[str, object] = field(default_factory=dict)
    schema_name: str | None = None


# --- AgentGuard ------------------------------------------------------------
# A production merge with incomplete tests: escalate to a human.
_AGENT_GUARD_MERGE = MockFixture(
    schema_name="ToolAuthorization",
    match={
        "agent": "deploy-agent",
        "tool": "github.merge",
        "repository": "production-repo",
        "tests_passed": False,
    },
    action="human_review",
    confidence=0.91,
    probabilities={"allow": 0.07, "human_review": 0.91, "deny": 0.02},
    risk=0.84,
    reason_codes=["production_repository", "merge_operation"],
)

_AGENT_GUARD_MERGE_SPEC = MockFixture(
    schema_name="ToolAuthorization",
    match={
        "agent": "deploy-agent",
        "tool": "github.merge",
        "repository": "org/project",
        "environment": "production",
        "tests_passed": False,
    },
    action="human_review",
    confidence=0.91,
    probabilities={"allow": 0.08, "human_review": 0.91, "deny": 0.01},
    risk=0.87,
    reason_codes=["production_repository", "merge_operation", "incomplete_tests"],
)

# Deleting production data is always denied at the model level too.
_AGENT_GUARD_DELETE_DATABASE = MockFixture(
    schema_name="ToolAuthorization",
    match={"tool": "database.delete"},
    action="deny",
    confidence=0.97,
    probabilities={"allow": 0.01, "human_review": 0.02, "deny": 0.97},
    risk=0.95,
    reason_codes=["destructive_operation"],
)

# Reading a file is routinely safe.
_AGENT_GUARD_READ_FILE = MockFixture(
    schema_name="ToolAuthorization",
    match={"tool": "read_file"},
    action="allow",
    confidence=0.99,
    probabilities={"allow": 0.99, "human_review": 0.009, "deny": 0.001},
    risk=0.02,
    reason_codes=["read_only_operation"],
)

# Rotating credentials in production warrants review.
_AGENT_GUARD_ROTATE_CREDENTIALS = MockFixture(
    schema_name="ToolAuthorization",
    match={"tool": "rotate_credentials"},
    action="human_review",
    confidence=0.78,
    probabilities={"allow": 0.12, "human_review": 0.78, "deny": 0.10},
    risk=0.61,
    reason_codes=["credential_operation", "production_repository"],
)

# --- Deployment rollback ---------------------------------------------------
_ROLLBACK_UNAVAILABLE = MockFixture(
    schema_name="DeploymentDecision",
    match={"rollback_available": False},
    action="human_review",
    confidence=0.72,
    probabilities={"continue": 0.10, "rollback": 0.06, "pause": 0.12, "human_review": 0.72},
    risk=0.66,
    reason_codes=["rollback_unavailable"],
)

_ROLLBACK_TRIGGERED = MockFixture(
    schema_name="DeploymentDecision",
    match={
        "recent_deployment": True,
        "rollback_available": True,
        "error_rate": 0.31,
    },
    action="rollback",
    confidence=0.91,
    probabilities={"continue": 0.03, "rollback": 0.91, "pause": 0.04, "human_review": 0.02},
    risk=0.88,
    reason_codes=["error_rate_spike", "latency_regression", "recent_deployment"],
)

# Order matters: more specific fixtures are listed first.
FIXTURES: tuple[MockFixture, ...] = (
    _AGENT_GUARD_MERGE_SPEC,
    _AGENT_GUARD_MERGE,
    _AGENT_GUARD_DELETE_DATABASE,
    _AGENT_GUARD_READ_FILE,
    _AGENT_GUARD_ROTATE_CREDENTIALS,
    _ROLLBACK_TRIGGERED,
    _ROLLBACK_UNAVAILABLE,
)

# Floats are rounded to a stable number of decimals when generating fallbacks
# so serialized output is byte-for-byte reproducible.
_FALLBACK_PRECISION = 6


__all__ = ["FIXTURES", "MockFixture"]
