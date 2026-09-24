"""Property tests for policy precedence.

The central invariant: a deterministic hard-deny policy can never be bypassed
by probabilistic model output. We generate arbitrary model decisions and
confirm that whenever a hard-deny rule fires, the final action is the deny
action regardless of what the model suggested.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from decisionos.models import Decision, DecisionSchema
from decisionos.policies import PolicyEvaluator, load_policy_yaml

SCHEMA = DecisionSchema(
    name="ToolAuthorization",
    version=1,
    actions=("allow", "human_review", "deny"),
)

DENY_POLICY = load_policy_yaml(
    """
    name: deny-high-risk
    rules:
      - name: high-risk
        when:
          risk: {gt: 0.9}
        action:
          require: deny
    """
)

REVIEW_POLICY = load_policy_yaml(
    """
    name: review-high-risk
    rules:
      - name: high-risk
        when:
          risk: {gt: 0.9}
        action:
          require: human_review
    """
)


def _decision(action: str, confidence: float, risk: float) -> Decision:
    probabilities = {name: 0.0 for name in SCHEMA.actions}
    probabilities[action] = 1.0
    return Decision(
        id="d",
        decision_type="t",
        schema_name="ToolAuthorization",
        schema_version=1,
        action=action,
        confidence=confidence,
        probabilities=probabilities,
        risk=risk,
        provider="hypothesis",
        latency_ms=0.0,
    )


@settings(max_examples=200)
@given(
    action=st.sampled_from(SCHEMA.actions),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    risk=st.floats(min_value=0.9, max_value=1.0, allow_nan=False).filter(lambda r: r > 0.9),
)
@pytest.mark.asyncio
async def test_hard_deny_always_wins(action: str, confidence: float, risk: float) -> None:
    evaluator = PolicyEvaluator(DENY_POLICY, SCHEMA)
    decision = _decision(action, confidence, risk)
    outcome = await evaluator.evaluate(decision, {})
    assert outcome.decision.action == "deny"
    assert outcome.decision.probabilities == decision.probabilities


@settings(max_examples=200)
@given(
    action=st.sampled_from(SCHEMA.actions),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    risk=st.floats(min_value=0.0, max_value=0.9, allow_nan=False),
)
@pytest.mark.asyncio
async def test_below_threshold_defers_to_model(action: str, confidence: float, risk: float) -> None:
    evaluator = PolicyEvaluator(DENY_POLICY, SCHEMA)
    outcome = await evaluator.evaluate(_decision(action, confidence, risk), {})
    assert outcome.decision.action == action
    assert outcome.overridden is False


@settings(max_examples=200)
@given(
    action=st.sampled_from(SCHEMA.actions),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    risk=st.floats(min_value=0.9, max_value=1.0, allow_nan=False).filter(lambda r: r > 0.9),
)
@pytest.mark.asyncio
async def test_review_policy_never_denies(action: str, confidence: float, risk: float) -> None:
    # A required-human-review policy must never escalate all the way to deny.
    evaluator = PolicyEvaluator(REVIEW_POLICY, SCHEMA)
    outcome = await evaluator.evaluate(_decision(action, confidence, risk), {})
    assert outcome.decision.action == "human_review"


@settings(max_examples=100)
@given(
    action=st.sampled_from(SCHEMA.actions),
    risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@pytest.mark.asyncio
async def test_policy_is_deterministic(action: str, risk: float) -> None:
    evaluator = PolicyEvaluator(DENY_POLICY, SCHEMA)
    decision = _decision(action, 0.5, risk)
    first = await evaluator.evaluate(decision, {})
    second = await evaluator.evaluate(decision, {})
    assert first.decision.action == second.decision.action
    assert first.overridden == second.overridden
    assert first.precedence == second.precedence
