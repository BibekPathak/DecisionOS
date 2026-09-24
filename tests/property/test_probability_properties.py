"""Property tests for probability distributions and the decision trust boundary.

Uses Hypothesis to generate probability distributions and confirm that:

* valid distributions (each ``p`` in ``[0, 1]``, summing to ~1) are accepted;
* any distribution with a component outside ``[0, 1]`` is rejected;
* any distribution whose mass is far from 1 is rejected.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from decisionos.models import (
    Decision,
    DecisionSchema,
    ProviderOutputError,
    RawDecision,
)

SCHEMA = DecisionSchema(name="S", version=1, actions=("a", "b", "c"))

# A probability strictly inside [0, 1].
_prob = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def _valid_distribution(draw: st.DrawFn) -> dict[str, float]:
    """Draw three non-negative values and normalize them to sum to 1."""
    values = draw(
        st.lists(
            st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=3,
            max_size=3,
        )
    )
    total = sum(values)
    return {"a": values[0] / total, "b": values[1] / total, "c": values[2] / total}


@settings(max_examples=200)
@given(distribution=_valid_distribution())
def test_valid_distributions_are_accepted(distribution: dict[str, float]) -> None:
    action = max(distribution, key=distribution.__getitem__)
    raw = RawDecision(
        action=action,
        probabilities=distribution,
        provider="hypothesis",
        latency_ms=1.0,
    )
    decision = Decision.from_raw(raw, decision_id="d", decision_type="t", schema=SCHEMA)
    assert sum(decision.probabilities.values()) == pytest.approx(1.0)
    assert all(0.0 <= p <= 1.0 for p in decision.probabilities.values())


@settings(max_examples=200)
@given(distribution=_valid_distribution())
def test_selected_action_is_always_present(distribution: dict[str, float]) -> None:
    action = max(distribution, key=distribution.__getitem__)
    raw = RawDecision(
        action=action,
        probabilities=distribution,
        provider="hypothesis",
        latency_ms=1.0,
    )
    decision = Decision.from_raw(raw, decision_id="d", decision_type="t", schema=SCHEMA)
    assert decision.action in decision.probabilities
    assert 0.0 <= decision.confidence <= 1.0
    assert decision.risk is None or 0.0 <= decision.risk <= 1.0


@settings(max_examples=200)
@given(
    values=st.lists(
        st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=3,
    )
)
def test_arbitrary_distributions_are_either_accepted_or_rejected(values: list[float]) -> None:
    """Any three floats either form a valid distribution or are rejected."""
    distribution = {"a": values[0], "b": values[1], "c": values[2]}
    raw = RawDecision(action="a", probabilities=distribution, provider="h", latency_ms=1.0)
    try:
        decision = Decision.from_raw(raw, decision_id="d", decision_type="t", schema=SCHEMA)
    except ProviderOutputError:
        return
    # If accepted, the invariants must hold.
    assert all(0.0 <= p <= 1.0 for p in decision.probabilities.values())
    assert math.isclose(sum(decision.probabilities.values()), 1.0, abs_tol=1e-6)


@given(
    share=st.floats(min_value=0.34, max_value=0.99, allow_nan=False, allow_infinity=False),
)
def test_distributions_summing_above_one_are_rejected(share: float) -> None:
    # Each component is individually valid but three of them sum to well over 1.
    distribution = {"a": share, "b": share, "c": share}
    raw = RawDecision(action="a", probabilities=distribution, provider="h", latency_ms=1.0)
    with pytest.raises(ProviderOutputError, match="not approximately 1"):
        Decision.from_raw(raw, decision_id="d", decision_type="t", schema=SCHEMA)


@given(
    bad=st.floats(min_value=1.0001, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_probability_above_one_alone_is_rejected(bad: float) -> None:
    distribution = {"a": bad, "b": 0.0, "c": 0.0}
    raw = RawDecision(action="a", probabilities=distribution, provider="h", latency_ms=1.0)
    with pytest.raises(ProviderOutputError):
        Decision.from_raw(raw, decision_id="d", decision_type="t", schema=SCHEMA)


@given(
    negative=st.floats(min_value=-100.0, max_value=-1e-3, allow_nan=False, allow_infinity=False),
)
def test_negative_probabilities_are_rejected(negative: float) -> None:
    # Keep the sum plausible so the failure is specifically about the sign.
    distribution = {"a": negative, "b": 1.0, "c": 0.0}
    raw = RawDecision(action="b", probabilities=distribution, provider="h", latency_ms=1.0)
    with pytest.raises(ProviderOutputError):
        Decision.from_raw(raw, decision_id="d", decision_type="t", schema=SCHEMA)
