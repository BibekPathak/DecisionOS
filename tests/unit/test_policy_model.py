"""Unit tests for the Policy structural model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from decisionos.models import Policy


def test_minimal_policy() -> None:
    policy = Policy(
        name="production-agent-policy",
        version=1,
        rules=(
            {"name": "high-risk", "when": {"risk": {"gt": 0.9}}, "action": {"require": "deny"}},
        ),
    )
    assert policy.key == "production-agent-policy@1"
    assert policy.rules[0].name == "high-risk"
    assert policy.rules[0].action.require == "deny"


def test_scalar_condition_accepted() -> None:
    policy = Policy(
        name="p",
        version=1,
        rules=({"name": "db", "when": {"tool": "database.delete"}, "action": {"require": "deny"}},),
    )
    assert policy.rules[0].when == {"tool": "database.delete"}


def test_rule_requires_at_least_one_condition() -> None:
    with pytest.raises(ValidationError):
        Policy(
            name="p", version=1, rules=({"name": "r", "when": {}, "action": {"require": "deny"}},)
        )


def test_empty_operator_mapping_rejected() -> None:
    with pytest.raises(ValidationError, match="condition for"):
        Policy(
            name="p",
            version=1,
            rules=({"name": "r", "when": {"risk": {}}, "action": {"require": "deny"}},),
        )


def test_unsupported_operator_rejected() -> None:
    with pytest.raises(ValidationError, match="unsupported operators"):
        Policy(
            name="p",
            version=1,
            rules=(
                {"name": "r", "when": {"risk": {"between": [0, 1]}}, "action": {"require": "deny"}},
            ),
        )


def test_policy_requires_at_least_one_rule() -> None:
    with pytest.raises(ValidationError):
        Policy(name="p", version=1, rules=())


def test_duplicate_rule_names_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate rule name"):
        Policy(
            name="p",
            version=1,
            rules=(
                {"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},
                {"name": "r", "when": {"b": 2}, "action": {"require": "allow"}},
            ),
        )


def test_blank_required_action_rejected() -> None:
    with pytest.raises(ValidationError):
        Policy(
            name="p",
            version=1,
            rules=({"name": "r", "when": {"a": 1}, "action": {"require": "  "}},),
        )


def test_policy_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Policy(
            name="p",
            version=0,
            rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},),
        )


def test_policy_is_frozen() -> None:
    policy = Policy(
        name="p",
        version=1,
        rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},),
    )
    with pytest.raises(ValidationError):
        policy.version = 2  # type: ignore[misc]
