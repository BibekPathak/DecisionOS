"""Unit tests for the decision lifecycle state machine."""

from __future__ import annotations

import pytest

from decisionos.engine import (
    ALLOWED_TRANSITIONS,
    FAILURE_STATES,
    TERMINAL_STATES,
    DecisionLifecycle,
    DecisionTerminalError,
    InvalidTransitionError,
)
from decisionos.models import DecisionEventType, DecisionState


def test_initial_state_and_event() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    assert lifecycle.state is DecisionState.CREATED
    assert lifecycle.is_terminal is False
    assert len(lifecycle.events) == 1
    assert lifecycle.events[0].type is DecisionEventType.CREATED
    assert lifecycle.events[0].to_state is DecisionState.CREATED


def test_blank_decision_id_rejected() -> None:
    with pytest.raises(ValueError):
        DecisionLifecycle("")


def test_happy_path_transitions() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    lifecycle.start_evaluation()
    lifecycle.complete_evaluation()
    lifecycle.complete_policy_evaluation()
    lifecycle.select_action()
    lifecycle.mark_executed()
    lifecycle.record_outcome()
    assert lifecycle.state is DecisionState.OUTCOME_RECORDED
    assert lifecycle.is_terminal is True


def test_default_event_types_are_specific() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    event = lifecycle.start_evaluation()
    assert event.type is DecisionEventType.EVALUATION_STARTED
    event = lifecycle.complete_evaluation()
    assert event.type is DecisionEventType.EVALUATION_COMPLETED


def test_skipping_states_is_rejected() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    with pytest.raises(InvalidTransitionError):
        lifecycle.select_action()


def test_backwards_transition_is_rejected() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    lifecycle.start_evaluation()
    lifecycle.complete_evaluation()
    with pytest.raises(InvalidTransitionError):
        lifecycle.transition(DecisionState.EVALUATING)


@pytest.mark.parametrize(
    "failure_state",
    [DecisionState.FAILED, DecisionState.EXPIRED, DecisionState.CANCELLED],
)
def test_failure_from_any_active_state(failure_state: DecisionState) -> None:
    lifecycle = DecisionLifecycle("dec_1")
    lifecycle.start_evaluation()
    lifecycle.transition(failure_state)
    assert lifecycle.state is failure_state
    assert lifecycle.is_terminal is True


def test_no_transition_after_terminal() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    lifecycle.fail()
    with pytest.raises(DecisionTerminalError):
        lifecycle.cancel()


def test_cannot_skip_straight_to_outcome() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    with pytest.raises(InvalidTransitionError):
        lifecycle.record_outcome()


def test_failure_state_is_terminal_for_all_states() -> None:
    for state in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[state] == frozenset()


def test_failure_states_are_terminals() -> None:
    assert FAILURE_STATES <= TERMINAL_STATES


def test_event_records_from_and_to() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    event = lifecycle.start_evaluation(provider="mock")
    assert event.from_state is DecisionState.CREATED
    assert event.to_state is DecisionState.EVALUATING
    assert event.payload == {"provider": "mock"}


def test_record_non_transition_event_keeps_state() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    event = lifecycle.record(DecisionEventType.STATE_TRANSITION, payload={"note": "x"})
    assert lifecycle.state is DecisionState.CREATED
    assert event.to_state is DecisionState.CREATED
    assert event.payload == {"note": "x"}


def test_can_transition_reflects_rules() -> None:
    lifecycle = DecisionLifecycle("dec_1")
    assert lifecycle.can_transition(DecisionState.EVALUATING) is True
    assert lifecycle.can_transition(DecisionState.EXECUTED) is False
    assert lifecycle.can_transition(DecisionState.FAILED) is True


def test_all_active_states_can_fail() -> None:
    for state in DecisionState:
        if state in TERMINAL_STATES:
            continue
        assert DecisionState.FAILED in ALLOWED_TRANSITIONS[state]


def test_invalid_transition_error_carries_states() -> None:
    error = InvalidTransitionError(DecisionState.CREATED, DecisionState.EXECUTED)
    assert error.current is DecisionState.CREATED
    assert error.target is DecisionState.EXECUTED
