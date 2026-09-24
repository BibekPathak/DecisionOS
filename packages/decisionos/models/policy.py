"""Policy definitions.

A policy is a deterministic rule set layered on top of a provider's
probabilistic output. Policies never consult a model: given the same decision
and context, a policy always resolves to the same required action.

This module defines the *shape* of a policy (parsed from YAML in Phase 4) and
its structural validation. Rule matching and precedence resolution live in
``decisionos.policies``.

A rule combines:

* ``when``: a map of field names to conditions. A scalar condition (e.g.
  ``tool: database.delete``) tests equality against values drawn from the
  decision context or the derived decision fields (``risk``, ``confidence``,
  ``action``). A mapping condition (e.g. ``risk: {gt: 0.9}``) applies an
  operator.
* ``action``: the required outcome, currently ``require: <action>``.

All conditions in a rule must match (logical AND) for the rule to fire.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from decisionos.models.enums import PolicyPrecedence

# Fields that may appear on the left-hand side of a condition and are derived
# from the decision itself rather than the raw context.
DERIVED_FIELDS: frozenset[str] = frozenset({"risk", "confidence", "action"})

# Well-known action names mapped to a default precedence category. Policies may
# override these via ``action_precedence``; unmapped actions default to
# ``MODEL_DECISION``. This lets the policy engine enforce that a required
# "deny" always outranks the model without hard-coding a single vocabulary.
DEFAULT_ACTION_PRECEDENCE: dict[str, PolicyPrecedence] = {
    "deny": PolicyPrecedence.HARD_DENY,
    "block": PolicyPrecedence.HARD_DENY,
    "reject": PolicyPrecedence.HARD_DENY,
    "human_review": PolicyPrecedence.REQUIRED_HUMAN_REVIEW,
    "review": PolicyPrecedence.REQUIRED_HUMAN_REVIEW,
    "escalate": PolicyPrecedence.REQUIRED_HUMAN_REVIEW,
    "pause": PolicyPrecedence.REQUIRED_HUMAN_REVIEW,
}

# Operators accepted inside a condition mapping.
SUPPORTED_OPERATORS: frozenset[str] = frozenset(
    {
        "eq",
        "neq",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "not_in",
        "regex",
        "exists",
    }
)


class PolicyRuleAction(BaseModel):
    """The action a fired rule requires."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    require: str = Field(min_length=1, max_length=64)

    @field_validator("require")
    @classmethod
    def _validate_require(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required action must not be blank")
        return value


class PolicyRule(BaseModel):
    """A single named rule with conditions and a required action."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    when: dict[str, Any] = Field(default_factory=dict)
    action: PolicyRuleAction

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rule name must not be blank")
        return value

    @field_validator("when")
    @classmethod
    def _validate_when(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("a rule must declare at least one condition")
        for field_name, condition in value.items():
            if isinstance(condition, dict):
                if not condition:
                    raise ValueError(f"condition for {field_name!r} is empty")
                unknown = set(condition) - SUPPORTED_OPERATORS
                if unknown:
                    raise ValueError(
                        f"condition for {field_name!r} uses unsupported operators: "
                        f"{sorted(unknown)}"
                    )
        return value


class Policy(BaseModel):
    """A named, versioned, immutable policy.

    Attributes
    ----------
    name:
        Policy identifier.
    version:
        Monotonic version, starting at 1.
    rules:
        Ordered rules. Rule order does not affect outcome given precedence is
        resolved by required action, but is preserved for explanation.
    description:
        Optional human-readable description.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    rules: tuple[PolicyRule, ...] = Field(min_length=1)
    description: str | None = None
    action_precedence: dict[str, PolicyPrecedence] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("policy name must not be blank")
        return value

    @field_validator("rules")
    @classmethod
    def _validate_rules(cls, value: tuple[PolicyRule, ...]) -> tuple[PolicyRule, ...]:
        seen: set[str] = set()
        for rule in value:
            if rule.name in seen:
                raise ValueError(f"duplicate rule name: {rule.name!r}")
            seen.add(rule.name)
        return value

    @model_validator(mode="after")
    def _validate_rule_targets(self) -> Policy:
        # ``when.action`` refers to the model's suggested action, so any value
        # is structurally valid here; membership in a schema is enforced when a
        # policy is bound to a decision.
        required = {rule.action.require for rule in self.rules}
        unknown = set(self.action_precedence) - required
        if unknown:
            raise ValueError(
                f"action_precedence references actions that no rule requires: {sorted(unknown)}"
            )
        return self

    def precedence_for(self, action: str) -> PolicyPrecedence:
        """Return the precedence category for ``action``.

        An explicit ``action_precedence`` entry wins; otherwise the
        well-known defaults apply, falling back to ``MODEL_DECISION``.
        """
        if action in self.action_precedence:
            return self.action_precedence[action]
        return DEFAULT_ACTION_PRECEDENCE.get(action, PolicyPrecedence.MODEL_DECISION)

    @property
    def key(self) -> str:
        """A stable ``name@version`` identifier."""
        return f"{self.name}@{self.version}"


__all__ = [
    "DEFAULT_ACTION_PRECEDENCE",
    "DERIVED_FIELDS",
    "SUPPORTED_OPERATORS",
    "Policy",
    "PolicyRule",
    "PolicyRuleAction",
]
