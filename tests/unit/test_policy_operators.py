"""Unit tests for policy condition operators."""

from __future__ import annotations

import pytest

from decisionos.policies import MISSING, PolicyOperatorError, evaluate_condition


def test_scalar_expectation_is_equality() -> None:
    assert evaluate_condition("tool", "database.delete", "database.delete").matched
    assert not evaluate_condition("tool", "read_file", "database.delete").matched


def test_eq_and_neq() -> None:
    assert evaluate_condition("x", "a", {"eq": "a"}).matched
    assert not evaluate_condition("x", "b", {"eq": "a"}).matched
    assert evaluate_condition("x", "b", {"neq": "a"}).matched
    assert not evaluate_condition("x", "a", {"neq": "a"}).matched


def test_numeric_equality_across_types() -> None:
    assert evaluate_condition("x", 1, {"eq": 1.0}).matched
    assert evaluate_condition("x", 1.0, {"eq": 1}).matched


def test_boolean_equality_is_strict() -> None:
    assert evaluate_condition("x", True, {"eq": True}).matched
    assert not evaluate_condition("x", True, {"eq": 1}).matched
    assert not evaluate_condition("x", 1, {"eq": True}).matched


@pytest.mark.parametrize(
    ("operator", "value", "operand", "expected"),
    [
        ("gt", 0.9, 0.5, True),
        ("gt", 0.5, 0.5, False),
        ("gte", 0.5, 0.5, True),
        ("lt", 0.1, 0.5, True),
        ("lt", 0.5, 0.5, False),
        ("lte", 0.5, 0.5, True),
    ],
)
def test_numeric_comparisons(operator: str, value: float, operand: float, expected: bool) -> None:
    assert evaluate_condition("risk", value, {operator: operand}).matched is expected


def test_in_and_not_in() -> None:
    assert evaluate_condition("tool", "a", {"in": ["a", "b"]}).matched
    assert not evaluate_condition("tool", "c", {"in": ["a", "b"]}).matched
    assert evaluate_condition("tool", "c", {"not_in": ["a", "b"]}).matched
    assert not evaluate_condition("tool", "a", {"not_in": ["a", "b"]}).matched


def test_in_requires_list_operand() -> None:
    with pytest.raises(PolicyOperatorError):
        evaluate_condition("tool", "a", {"in": "a"})


def test_regex_match() -> None:
    assert evaluate_condition("repo", "org/prod-repo", {"regex": "prod-.*"}).matched
    assert not evaluate_condition("repo", "org/dev-repo", {"regex": "prod-.*"}).matched


def test_invalid_regex_raises() -> None:
    with pytest.raises(PolicyOperatorError, match="invalid regex"):
        evaluate_condition("repo", "x", {"regex": "("})


def test_regex_too_long_raises() -> None:
    with pytest.raises(PolicyOperatorError, match="exceeds"):
        evaluate_condition("repo", "x", {"regex": "a" * 513})


def test_exists() -> None:
    assert evaluate_condition("x", 1, {"exists": True}).matched
    assert evaluate_condition("x", None, {"exists": False}).matched
    assert evaluate_condition("x", MISSING, {"exists": False}).matched
    assert not evaluate_condition("x", MISSING, {"exists": True}).matched


def test_numeric_operator_on_string_raises() -> None:
    with pytest.raises(PolicyOperatorError, match="expected a number"):
        evaluate_condition("risk", "high", {"gt": 0.5})


def test_numeric_operator_on_missing_raises() -> None:
    with pytest.raises(PolicyOperatorError, match="missing"):
        evaluate_condition("risk", MISSING, {"gt": 0.5})


def test_missing_value_eq_is_false() -> None:
    assert not evaluate_condition("x", MISSING, {"eq": "a"}).matched


def test_missing_value_neq_is_true() -> None:
    assert evaluate_condition("x", MISSING, {"neq": "a"}).matched


def test_empty_mapping_rejected() -> None:
    with pytest.raises(PolicyOperatorError, match="empty"):
        evaluate_condition("x", 1, {})


def test_multiple_operators_must_all_hold() -> None:
    assert evaluate_condition("risk", 0.95, {"gt": 0.9, "lt": 1.0}).matched
    assert not evaluate_condition("risk", 0.95, {"gt": 0.9, "lt": 0.95}).matched


def test_matched_result_carries_detail() -> None:
    result = evaluate_condition("risk", 0.95, {"gt": 0.9})
    assert result.matched
    assert "risk gt 0.9" in result.detail
