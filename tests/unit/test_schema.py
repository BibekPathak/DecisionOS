"""Unit tests for DecisionSchema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from decisionos.models import DecisionSchema


def test_minimal_schema() -> None:
    schema = DecisionSchema(name="ToolAuthorization", version=1, actions=("allow", "deny"))
    assert schema.key == "ToolAuthorization@1"
    assert schema.has_action("allow")
    assert not schema.has_action("merge")


def test_schema_is_frozen() -> None:
    schema = DecisionSchema(name="S", version=1, actions=("allow", "deny"))
    with pytest.raises(ValidationError):
        schema.version = 2  # type: ignore[misc]


def test_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        DecisionSchema(name="S", version=0, actions=("allow",))


def test_actions_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        DecisionSchema(name="S", version=1, actions=())


def test_duplicate_actions_rejected() -> None:
    with pytest.raises(ValidationError):
        DecisionSchema(name="S", version=1, actions=("allow", "allow"))


def test_blank_action_rejected() -> None:
    with pytest.raises(ValidationError):
        DecisionSchema(name="S", version=1, actions=("allow", " "))  # type: ignore[arg-type]


def test_action_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        DecisionSchema(name="S", version=1, actions=("x" * 65,))


def test_name_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        DecisionSchema(name="   ", version=1, actions=("allow",))


def test_jev_criteria_includes_all_actions_with_none_defaults() -> None:
    schema = DecisionSchema(name="S", version=1, actions=("allow", "deny"))
    assert schema.jev_criteria() == {"allow": None, "deny": None}


def test_jev_criteria_uses_action_descriptions() -> None:
    schema = DecisionSchema(
        name="S",
        version=1,
        actions=("allow", "deny"),
        action_descriptions={"allow": "Permitted", "deny": "Forbidden"},
    )
    assert schema.jev_criteria() == {"allow": "Permitted", "deny": "Forbidden"}


def test_action_descriptions_must_reference_known_actions() -> None:
    with pytest.raises(ValidationError):
        DecisionSchema(
            name="S",
            version=1,
            actions=("allow",),
            action_descriptions={"merge": "not an action"},
        )


def test_new_version_is_a_distinct_schema() -> None:
    v1 = DecisionSchema(name="S", version=1, actions=("allow", "deny"))
    v2 = DecisionSchema(name="S", version=2, actions=("allow", "deny", "review"))
    assert v1.key != v2.key
    assert not v1.has_action("review")
    assert v2.has_action("review")
