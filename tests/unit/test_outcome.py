"""Unit tests for Outcome."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from decisionos.models import Outcome


def test_minimal_outcome() -> None:
    outcome = Outcome(decision_id="dec_1", actual_outcome="safe", success=True)
    assert outcome.decision_id == "dec_1"
    assert outcome.actual_outcome == "safe"
    assert outcome.success is True
    assert outcome.metadata == {}


def test_blank_actual_outcome_rejected() -> None:
    with pytest.raises(ValidationError):
        Outcome(decision_id="dec_1", actual_outcome="  ", success=True)


def test_blank_decision_id_rejected() -> None:
    with pytest.raises(ValidationError):
        Outcome(decision_id="", actual_outcome="safe", success=True)


def test_metadata_is_preserved() -> None:
    outcome = Outcome(
        decision_id="dec_1",
        actual_outcome="unsafe",
        success=False,
        metadata={"source": "postmortem"},
    )
    assert outcome.metadata == {"source": "postmortem"}


def test_outcome_is_frozen() -> None:
    outcome = Outcome(decision_id="dec_1", actual_outcome="safe", success=True)
    with pytest.raises(ValidationError):
        outcome.success = False  # type: ignore[misc]


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Outcome(  # type: ignore[call-arg]
            decision_id="dec_1",
            actual_outcome="safe",
            success=True,
            unexpected="x",
        )
