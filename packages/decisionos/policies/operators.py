"""Condition operators for the policy engine.

A condition compares a value drawn from the decision context (or a derived
decision field such as ``risk``/``confidence``/``action``) against a rule's
expectation. Conditions are deterministic: given the same value and
expectation, the result is always the same.

Supported forms:

* A scalar expectation, e.g. ``tool: database.delete``, is an implicit equality
  test.
* A mapping expectation applies one or more operators, e.g.
  ``risk: {gt: 0.9}``. When a mapping supplies several operators they must all
  hold (logical AND).

Type errors are explicit: comparing a string to a number raises
``PolicyOperatorError`` rather than silently returning false, so a malformed
policy surfaces at evaluation time instead of hiding a security decision.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Regex patterns are bounded to guard against pathological input cost.
_MAX_REGEX_LENGTH = 512


class PolicyOperatorError(ValueError):
    """Raised when a condition cannot be evaluated against a value."""


@dataclass(frozen=True)
class OperatorResult:
    """The result of evaluating one operator.

    Attributes
    ----------
    matched:
        Whether the condition held.
    detail:
        A short, structured explanation suitable for audit output.
    """

    matched: bool
    detail: str = ""


_MISSING = object()


def evaluate_condition(field: str, value: Any, expectation: Any) -> OperatorResult:
    """Evaluate ``expectation`` against ``value`` for ``field``.

    A scalar expectation is treated as equality. A mapping expectation applies
    each operator; all must hold.
    """
    if isinstance(expectation, Mapping):
        if not expectation:
            raise PolicyOperatorError(f"condition for {field!r} is empty")
        details: list[str] = []
        matched = True
        for operator, operand in expectation.items():
            result = _apply_operator(field, operator, value, operand)
            details.append(result.detail)
            if not result.matched:
                matched = False
                # Keep evaluating to produce a complete explanation only when
                # the failed operator's detail is needed; short-circuit is
                # avoided so messages stay deterministic across operators.
        return OperatorResult(matched=matched, detail="; ".join(d for d in details if d))
    return _apply_operator(field, "eq", value, expectation)


def _apply_operator(field: str, operator: str, value: Any, operand: Any) -> OperatorResult:
    handler = _OPERATORS.get(operator)
    if handler is None:
        raise PolicyOperatorError(f"unsupported operator {operator!r} for field {field!r}")
    return handler(field, value, operand)


def _describe(field: str, operator: str, operand: Any) -> str:
    rendered = operand if not isinstance(operand, re.Pattern) else operand.pattern
    return f"{field} {operator} {rendered!r}"


def _op_exists(field: str, value: Any, operand: Any) -> OperatorResult:
    expected = bool(operand)
    present = value is not _MISSING and value is not None
    return OperatorResult(
        matched=present is expected,
        detail=f"{field} exists={present}",
    )


def _op_eq(field: str, value: Any, operand: Any) -> OperatorResult:
    if value is _MISSING:
        return OperatorResult(False, f"{field} is missing")
    matched = _equals(value, operand)
    return OperatorResult(matched, _describe(field, "eq", operand) if matched else "")


def _op_neq(field: str, value: Any, operand: Any) -> OperatorResult:
    if value is _MISSING:
        return OperatorResult(True, f"{field} is missing")
    matched = not _equals(value, operand)
    return OperatorResult(matched, _describe(field, "neq", operand) if matched else "")


def _op_gt(field: str, value: Any, operand: Any) -> OperatorResult:
    return _compare(field, value, operand, "gt", lambda a, b: a > b)


def _op_gte(field: str, value: Any, operand: Any) -> OperatorResult:
    return _compare(field, value, operand, "gte", lambda a, b: a >= b)


def _op_lt(field: str, value: Any, operand: Any) -> OperatorResult:
    return _compare(field, value, operand, "lt", lambda a, b: a < b)


def _op_lte(field: str, value: Any, operand: Any) -> OperatorResult:
    return _compare(field, value, operand, "lte", lambda a, b: a <= b)


def _compare(field: str, value: Any, operand: Any, operator: str, fn: Any) -> OperatorResult:
    left = _as_number(field, value, operator)
    right = _as_number(field, operand, operator, side="operand")
    matched = fn(left, right)
    return OperatorResult(matched, _describe(field, operator, operand) if matched else "")


def _op_in(field: str, value: Any, operand: Any) -> OperatorResult:
    options = _as_sequence(field, operand, "in")
    if value is _MISSING:
        return OperatorResult(False, f"{field} is missing")
    matched = any(_equals(value, option) for option in options)
    return OperatorResult(matched, _describe(field, "in", list(options)) if matched else "")


def _op_not_in(field: str, value: Any, operand: Any) -> OperatorResult:
    options = _as_sequence(field, operand, "not_in")
    if value is _MISSING:
        return OperatorResult(True, f"{field} is missing")
    matched = all(not _equals(value, option) for option in options)
    return OperatorResult(matched, _describe(field, "not_in", list(options)) if matched else "")


def _op_regex(field: str, value: Any, operand: Any) -> OperatorResult:
    pattern = _as_pattern(field, operand)
    if value is _MISSING or value is None:
        return OperatorResult(False, f"{field} is missing")
    matched = pattern.search(str(value)) is not None
    return OperatorResult(matched, _describe(field, "regex", pattern) if matched else "")


_OPERATORS: dict[str, Any] = {
    "exists": _op_exists,
    "eq": _op_eq,
    "neq": _op_neq,
    "gt": _op_gt,
    "gte": _op_gte,
    "lt": _op_lt,
    "lte": _op_lte,
    "in": _op_in,
    "not_in": _op_not_in,
    "regex": _op_regex,
}


def _equals(left: Any, right: Any) -> bool:
    """Compare two values, treating ints and floats as numerically equal."""
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if _is_number(left) and _is_number(right):
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-12)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return list(left) == list(right)
    return bool(left == right)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_number(field: str, value: Any, operator: str, *, side: str = "value") -> float:
    if value is _MISSING or value is None:
        raise PolicyOperatorError(
            f"cannot apply {operator!r} to {side} of field {field!r}: value is missing"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyOperatorError(
            f"cannot apply {operator!r} to {side} of field {field!r}: "
            f"expected a number, got {type(value).__name__}"
        )
    return float(value)


def _as_sequence(field: str, operand: Any, operator: str) -> Sequence[Any]:
    if isinstance(operand, (str, bytes)) or not isinstance(operand, Sequence):
        raise PolicyOperatorError(
            f"operator {operator!r} for field {field!r} requires a list operand"
        )
    return operand


def _as_pattern(field: str, operand: Any) -> re.Pattern[str]:
    if isinstance(operand, re.Pattern):
        return operand
    if not isinstance(operand, str):
        raise PolicyOperatorError(f"operator 'regex' for field {field!r} requires a string pattern")
    if len(operand) > _MAX_REGEX_LENGTH:
        raise PolicyOperatorError(
            f"regex for field {field!r} exceeds {_MAX_REGEX_LENGTH} characters"
        )
    try:
        return re.compile(operand)
    except re.error as error:
        raise PolicyOperatorError(f"invalid regex for field {field!r}: {error}") from error


__all__ = [
    "MISSING",
    "OperatorResult",
    "PolicyOperatorError",
    "evaluate_condition",
]

# Public sentinel name used by callers that need to test for absence.
MISSING = _MISSING
