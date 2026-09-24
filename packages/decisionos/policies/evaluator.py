"""Policy evaluation.

Given a validated :class:`Decision` and the request ``context``, the policy
evaluator:

1. builds an evaluation namespace from the context plus derived decision
   fields (``action``, ``confidence``, ``risk``),
2. matches every rule (all of a rule's conditions must hold),
3. resolves precedence across the rules that fired, and
4. produces the final action.

Precedence is strict and deterministic::

    HARD_DENY  >  REQUIRED_HUMAN_REVIEW  >  MODEL_DECISION

A higher-precedence required action always wins. A rule whose required action
carries ``MODEL_DECISION`` precedence *endorses* the model's action but does not
change it; policy can force a safer action, never a less safe one, because
``HARD_DENY`` and ``REQUIRED_HUMAN_REVIEW`` outrank it.

The evaluator is synchronous and pure with respect to a given (decision,
context): it never consults a provider and never mutates its inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decisionos.engine.evaluator import PolicyOutcome
from decisionos.models import (
    Decision,
    DecisionSchema,
    Policy,
    PolicyPrecedence,
    PolicyRule,
)
from decisionos.policies.operators import MISSING, PolicyOperatorError, evaluate_condition

# Rank of each precedence tier. Higher wins.
_PRECEDENCE_RANK: dict[PolicyPrecedence, int] = {
    PolicyPrecedence.MODEL_DECISION: 0,
    PolicyPrecedence.REQUIRED_HUMAN_REVIEW: 1,
    PolicyPrecedence.HARD_DENY: 2,
}


class PolicyEvaluationError(ValueError):
    """Raised when a policy cannot be evaluated against a decision."""


@dataclass(frozen=True)
class TriggeredRule:
    """A rule that fired, with its matched details."""

    name: str
    required_action: str
    precedence: PolicyPrecedence
    details: list[str]
    order: int


class PolicyEvaluator:
    """Evaluates a single :class:`Policy` against decisions.

    Parameters
    ----------
    policy:
        The policy to apply.
    schema:
        Optional schema the policy is bound to. When supplied, every required
        action must be one of the schema's actions; a mismatch is a
        configuration error, not a silent no-op.
    """

    def __init__(self, policy: Policy, schema: DecisionSchema | None = None) -> None:
        self._policy = policy
        self._schema = schema
        if schema is not None:
            self._validate_against_schema()

    @property
    def policy(self) -> Policy:
        return self._policy

    @property
    def schema(self) -> DecisionSchema | None:
        return self._schema

    async def evaluate(self, decision: Decision, context: dict[str, object]) -> PolicyOutcome:
        """Apply the policy to ``decision`` given ``context``."""
        namespace = self._build_namespace(decision, context)
        triggered = self._match_rules(namespace)

        if not triggered:
            return PolicyOutcome(
                decision=decision,
                triggered_rules=[],
                precedence=PolicyPrecedence.MODEL_DECISION.value,
                overridden=False,
            )

        winner = max(triggered, key=_rule_rank)
        precedence = winner.precedence
        triggered_names = [rule.name for rule in triggered]

        if precedence is PolicyPrecedence.MODEL_DECISION:
            # The model's action stands; rules are recorded but do not force.
            return PolicyOutcome(
                decision=decision,
                triggered_rules=triggered_names,
                precedence=precedence.value,
                overridden=False,
            )

        if winner.required_action == decision.action:
            # Policy agrees with the model; not an override.
            return PolicyOutcome(
                decision=decision,
                triggered_rules=triggered_names,
                precedence=precedence.value,
                overridden=False,
            )

        policy_decision = decision.with_action(
            winner.required_action,
            reason_codes=_merge_reason_codes(
                decision.reason_codes,
                [f"policy:{winner.name}", f"precedence:{precedence.value}"],
            ),
        )
        return PolicyOutcome(
            decision=policy_decision,
            triggered_rules=triggered_names,
            precedence=precedence.value,
            overridden=True,
        )

    # -- internal ---------------------------------------------------------

    def _build_namespace(self, decision: Decision, context: dict[str, object]) -> dict[str, Any]:
        namespace: dict[str, Any] = dict(context)
        # Derived fields are authoritative: they reflect the validated decision,
        # so a context cannot spoof confidence/risk/action to bypass policy.
        namespace["action"] = decision.action
        namespace["confidence"] = decision.confidence
        namespace["risk"] = decision.risk
        return namespace

    def _match_rules(self, namespace: dict[str, Any]) -> list[TriggeredRule]:
        triggered: list[TriggeredRule] = []
        for order, rule in enumerate(self._policy.rules):
            details = self._match_rule(rule, namespace)
            if details is None:
                continue
            triggered.append(
                TriggeredRule(
                    name=rule.name,
                    required_action=rule.action.require,
                    precedence=self._policy.precedence_for(rule.action.require),
                    details=details,
                    order=order,
                )
            )
        return triggered

    @staticmethod
    def _match_rule(rule: PolicyRule, namespace: dict[str, Any]) -> list[str] | None:
        details: list[str] = []
        for field, expectation in rule.when.items():
            value = namespace.get(field, MISSING)
            try:
                result = evaluate_condition(field, value, expectation)
            except PolicyOperatorError as error:
                raise PolicyEvaluationError(f"rule {rule.name!r}: {error}") from error
            if not result.matched:
                return None
            if result.detail:
                details.append(result.detail)
        return details

    def _validate_against_schema(self) -> None:
        assert self._schema is not None
        unknown = [
            rule.action.require
            for rule in self._policy.rules
            if not self._schema.has_action(rule.action.require)
        ]
        if unknown:
            raise PolicyEvaluationError(
                f"policy {self._policy.key} requires actions not in schema "
                f"{self._schema.key}: {sorted(set(unknown))}"
            )


def _rule_rank(rule: TriggeredRule) -> tuple[int, int]:
    """Sort key selecting the winning rule: precedence, then declaration order.

    ``max`` with this key picks the highest precedence; ties resolve to the
    earliest-declared rule because earlier rules have a larger negative index.
    """
    return (_PRECEDENCE_RANK[rule.precedence], -rule.order)


def _merge_reason_codes(existing: list[str], additions: list[str]) -> list[str]:
    merged = list(existing)
    for code in additions:
        if code not in merged:
            merged.append(code)
    return merged


__all__ = [
    "PolicyEvaluationError",
    "PolicyEvaluator",
    "TriggeredRule",
]
