"""Unit tests for Decision and the provider trust boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from decisionos.models import (
    Decision,
    DecisionSchema,
    ProviderOutputError,
    RawDecision,
)

SCHEMA = DecisionSchema(
    name="ToolAuthorization", version=1, actions=("allow", "human_review", "deny")
)


def _raw(**overrides: object) -> RawDecision:
    base: dict[str, object] = {
        "action": "human_review",
        "confidence": 0.91,
        "probabilities": {"allow": 0.08, "human_review": 0.91, "deny": 0.01},
        "risk": 0.87,
        "provider": "mock",
        "latency_ms": 84.0,
    }
    base.update(overrides)
    return RawDecision(**base)  # type: ignore[arg-type]


def _decision(raw: RawDecision, schema: DecisionSchema = SCHEMA) -> Decision:
    return Decision.from_raw(
        raw,
        decision_id="dec_1",
        decision_type="tool_authorization",
        schema=schema,
    )


def test_from_raw_builds_valid_decision() -> None:
    decision = _decision(_raw())
    assert decision.id == "dec_1"
    assert decision.action == "human_review"
    assert decision.confidence == 0.91
    assert decision.risk == 0.87
    assert decision.schema_key == "ToolAuthorization@1"
    assert decision.provider == "mock"
    assert decision.latency_ms == 84.0


def test_reason_codes_are_deduplicated_in_order() -> None:
    decision = _decision(_raw(reason_codes=["a", "b", "a"]))
    assert decision.reason_codes == ["a", "b"]


def test_action_outside_schema_is_rejected() -> None:
    with pytest.raises(ProviderOutputError, match="not in schema"):
        _decision(_raw(action="merge", probabilities={"allow": 0.5, "deny": 0.5}))


def test_missing_action_is_rejected() -> None:
    with pytest.raises(ProviderOutputError, match="did not return an action"):
        _decision(_raw(action=None))


def test_missing_probabilities_rejected() -> None:
    with pytest.raises(ProviderOutputError, match="did not return probabilities"):
        _decision(_raw(probabilities={}))


def test_probabilities_sum_far_from_one_rejected() -> None:
    with pytest.raises(ProviderOutputError, match="not approximately 1"):
        _decision(_raw(probabilities={"allow": 0.5, "deny": 0.2}))


def test_negative_probability_rejected() -> None:
    with pytest.raises(ProviderOutputError, match="negative"):
        _decision(_raw(probabilities={"allow": -0.1, "deny": 1.1}))


def test_probability_above_one_rejected() -> None:
    with pytest.raises(ProviderOutputError, match="exceeds 1"):
        _decision(_raw(probabilities={"allow": 1.5, "deny": 0.0}))


def test_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ProviderOutputError, match="confidence out of range"):
        _decision(_raw(confidence=1.5))


def test_risk_out_of_range_rejected() -> None:
    with pytest.raises(ProviderOutputError, match="risk out of range"):
        _decision(_raw(risk=-0.5))


def test_missing_risk_is_derived_from_distribution() -> None:
    decision = _decision(
        _raw(risk=None, action="allow", probabilities={"allow": 0.97, "deny": 0.03})
    )
    assert decision.risk == pytest.approx(0.03)


def test_missing_confidence_falls_back_to_selected_probability() -> None:
    decision = _decision(
        _raw(confidence=None, action="allow", probabilities={"allow": 0.97, "deny": 0.03})
    )
    assert decision.confidence == pytest.approx(0.97)


def test_tiny_float_excursions_are_normalized() -> None:
    raw = _raw(
        action="allow",
        probabilities={"allow": 0.9999999999, "deny": 1e-10},
    )
    decision = _decision(raw)
    assert sum(decision.probabilities.values()) == pytest.approx(1.0)


def test_selected_action_must_be_in_probabilities_when_constructed_directly() -> None:
    with pytest.raises(ValidationError, match="not present in probabilities"):
        Decision(
            id="d",
            decision_type="t",
            schema_name="S",
            schema_version=1,
            action="allow",
            confidence=0.5,
            probabilities={"deny": 1.0},
            provider="mock",
            latency_ms=1.0,
        )


def test_direct_construction_validates_ranges() -> None:
    with pytest.raises(ValidationError):
        Decision(
            id="d",
            decision_type="t",
            schema_name="S",
            schema_version=1,
            action="allow",
            confidence=2.0,
            probabilities={"allow": 1.0},
            provider="mock",
            latency_ms=1.0,
        )


def test_with_action_preserves_distribution() -> None:
    decision = _decision(_raw())
    overridden = decision.with_action("deny", reason_codes=["policy:hard-deny"])
    assert overridden.action == "deny"
    assert overridden.probabilities == decision.probabilities
    assert overridden.confidence == decision.confidence
    assert overridden.reason_codes == ["policy:hard-deny"]


def test_with_action_defaults_to_existing_reason_codes() -> None:
    decision = _decision(_raw(reason_codes=["x"]))
    assert decision.with_action("deny").reason_codes == ["x"]


def test_decision_is_frozen() -> None:
    decision = _decision(_raw())
    with pytest.raises(ValidationError):
        decision.action = "deny"  # type: ignore[misc]
