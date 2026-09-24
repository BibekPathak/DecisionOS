"""Unit tests for the policy evaluator and precedence resolution."""

from __future__ import annotations

import pytest

from decisionos.models import Decision, DecisionSchema, Policy, PolicyPrecedence
from decisionos.policies import (
    PolicyEvaluationError,
    PolicyEvaluator,
    load_policy_yaml,
)

SCHEMA = DecisionSchema(
    name="ToolAuthorization",
    version=1,
    actions=("allow", "human_review", "deny"),
)

SPEC_YAML = """
name: production-agent-policy
version: 1
rules:
  - name: dangerous-database-operation
    when:
      tool: database.delete
    action:
      require: deny
  - name: production-merge
    when:
      environment: production
      tool: github.merge
    action:
      require: human_review
  - name: high-risk
    when:
      risk:
        gt: 0.90
    action:
      require: deny
  - name: low-confidence
    when:
      confidence:
        lt: 0.70
    action:
      require: human_review
"""


def _decision(
    action: str = "allow", confidence: float = 0.97, risk: float | None = 0.1
) -> Decision:
    probabilities = {name: 0.0 for name in SCHEMA.actions}
    probabilities[action] = 1.0
    return Decision(
        id="dec_1",
        decision_type="tool_authorization",
        schema_name="ToolAuthorization",
        schema_version=1,
        action=action,
        confidence=confidence,
        probabilities=probabilities,
        risk=risk,
        provider="mock",
        latency_ms=1.0,
    )


@pytest.mark.asyncio
async def test_no_matching_rule_keeps_model_action() -> None:
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(_decision("allow", risk=0.1), {"tool": "read_file"})
    assert outcome.decision.action == "allow"
    assert outcome.overridden is False
    assert outcome.triggered_rules == []
    assert outcome.precedence == PolicyPrecedence.MODEL_DECISION.value


@pytest.mark.asyncio
async def test_model_allow_with_hard_deny_rule_is_denied() -> None:
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(_decision("allow", risk=0.95), {"tool": "read_file"})
    assert outcome.decision.action == "deny"
    assert outcome.overridden is True
    assert outcome.precedence == PolicyPrecedence.HARD_DENY.value
    assert "high-risk" in outcome.triggered_rules


@pytest.mark.asyncio
async def test_database_delete_requires_deny() -> None:
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(_decision("allow", risk=0.01), {"tool": "database.delete"})
    assert outcome.decision.action == "deny"
    assert outcome.overridden is True


@pytest.mark.asyncio
async def test_production_merge_requires_human_review() -> None:
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(
        _decision("allow", risk=0.1), {"environment": "production", "tool": "github.merge"}
    )
    assert outcome.decision.action == "human_review"
    assert outcome.precedence == PolicyPrecedence.REQUIRED_HUMAN_REVIEW.value


@pytest.mark.asyncio
async def test_low_confidence_requires_human_review() -> None:
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(_decision("allow", confidence=0.5, risk=0.1), {"tool": "x"})
    assert outcome.decision.action == "human_review"


@pytest.mark.asyncio
async def test_hard_deny_outranks_human_review() -> None:
    # Both a deny rule and a review rule fire; deny must win.
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(
        _decision("allow", confidence=0.5, risk=0.95),
        {"environment": "production", "tool": "github.merge"},
    )
    assert outcome.decision.action == "deny"
    assert outcome.precedence == PolicyPrecedence.HARD_DENY.value
    assert set(outcome.triggered_rules) >= {"high-risk", "production-merge"}


@pytest.mark.asyncio
async def test_policy_agreement_is_not_an_override() -> None:
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(
        _decision("human_review", risk=0.1),
        {"environment": "production", "tool": "github.merge"},
    )
    assert outcome.decision.action == "human_review"
    assert outcome.overridden is False
    assert "production-merge" in outcome.triggered_rules


@pytest.mark.asyncio
async def test_override_appends_reason_codes() -> None:
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(_decision("allow", risk=0.95), {"tool": "read_file"})
    assert "policy:high-risk" in outcome.decision.reason_codes
    assert f"precedence:{PolicyPrecedence.HARD_DENY.value}" in outcome.decision.reason_codes


@pytest.mark.asyncio
async def test_derived_fields_cannot_be_spoofed_by_context() -> None:
    # Context claims a high risk, but the decision's derived risk is low; the
    # rule must not fire because derived fields are authoritative.
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    outcome = await evaluator.evaluate(_decision("allow", risk=0.05), {"risk": 0.99})
    assert outcome.overridden is False


@pytest.mark.asyncio
async def test_tie_broken_by_declaration_order() -> None:
    policy = load_policy_yaml(
        """
        name: tie
        rules:
          - name: first
            when: {tool: x}
            action: {require: deny}
          - name: second
            when: {tool: x}
            action: {require: deny}
        """
    )
    evaluator = PolicyEvaluator(policy, SCHEMA)
    outcome = await evaluator.evaluate(_decision("allow"), {"tool": "x"})
    assert outcome.decision.action == "deny"


@pytest.mark.asyncio
async def test_required_action_must_belong_to_schema() -> None:
    policy = Policy(
        name="bad",
        version=1,
        rules=({"name": "r", "when": {"tool": "x"}, "action": {"require": "explode"}},),
    )
    with pytest.raises(PolicyEvaluationError, match="not in schema"):
        PolicyEvaluator(policy, SCHEMA)


@pytest.mark.asyncio
async def test_type_error_in_condition_raises_evaluation_error() -> None:
    bad_policy = load_policy_yaml(
        """
        name: typed
        rules:
          - name: r
            when:
              port: {gt: 1000}
            action: {require: deny}
        """
    )
    evaluator = PolicyEvaluator(bad_policy, SCHEMA)
    with pytest.raises(PolicyEvaluationError, match="rule 'r'"):
        await evaluator.evaluate(_decision("allow"), {"port": "not-a-number"})


@pytest.mark.asyncio
async def test_evaluator_does_not_mutate_input_decision() -> None:
    evaluator = PolicyEvaluator(load_policy_yaml(SPEC_YAML), SCHEMA)
    decision = _decision("allow", risk=0.95)
    original_probs = dict(decision.probabilities)
    outcome = await evaluator.evaluate(decision, {"tool": "read_file"})
    assert decision.action == "allow"
    assert decision.probabilities == original_probs
    assert outcome.decision.action == "deny"
    # The distribution is preserved even when the action is overridden.
    assert outcome.decision.probabilities == original_probs
