"""Decision lifecycle state machine and audit events.

Every decision moves through an explicit, auditable sequence of states. The
state machine enforces that only legal transitions occur and records an audit
event for each one, so a decision's full history can be reconstructed.

Happy path::

    CREATED -> EVALUATING -> EVALUATED -> POLICY_EVALUATED
            -> ACTION_SELECTED -> EXECUTED -> OUTCOME_RECORDED

Failure states (``FAILED``, ``EXPIRED``, ``CANCELLED``) may be entered from any
active state and are terminal. Once any terminal state is reached, no further
transitions are permitted.

Phase 5 persists these events; this module owns the rules and the in-memory
representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from decisionos.models.enums import DecisionEventType, DecisionState

# The ordered happy path. A transition that advances along this path is
# "forward"; the lifecycle also allows entry into failure states from any
# non-terminal state.
_HAPPY_PATH: tuple[DecisionState, ...] = (
    DecisionState.CREATED,
    DecisionState.EVALUATING,
    DecisionState.EVALUATED,
    DecisionState.POLICY_EVALUATED,
    DecisionState.ACTION_SELECTED,
    DecisionState.EXECUTED,
    DecisionState.OUTCOME_RECORDED,
)

FAILURE_STATES: frozenset[DecisionState] = frozenset(
    {DecisionState.FAILED, DecisionState.EXPIRED, DecisionState.CANCELLED}
)

TERMINAL_STATES: frozenset[DecisionState] = frozenset(
    {
        DecisionState.OUTCOME_RECORDED,
        DecisionState.FAILED,
        DecisionState.EXPIRED,
        DecisionState.CANCELLED,
    }
)


def _build_allowed_transitions() -> dict[DecisionState, frozenset[DecisionState]]:
    allowed: dict[DecisionState, set[DecisionState]] = {state: set() for state in DecisionState}
    # Forward edges along the happy path.
    for current, following in pairwise(_HAPPY_PATH):
        allowed[current].add(following)
    # Any non-terminal state may fail, expire, or be cancelled.
    for state in DecisionState:
        if state not in TERMINAL_STATES:
            allowed[state].update(FAILURE_STATES)
    # Terminal states have no outgoing transitions.
    for state in TERMINAL_STATES:
        allowed[state] = set()
    return {state: frozenset(targets) for state, targets in allowed.items()}


ALLOWED_TRANSITIONS: dict[DecisionState, frozenset[DecisionState]] = _build_allowed_transitions()


class InvalidTransitionError(ValueError):
    """Raised when a decision is moved along a disallowed transition."""

    def __init__(self, current: DecisionState, target: DecisionState) -> None:
        super().__init__(f"cannot transition from {current.value!r} to {target.value!r}")
        self.current = current
        self.target = target


class DecisionTerminalError(ValueError):
    """Raised when a transition is attempted on a terminal decision."""

    def __init__(self, current: DecisionState) -> None:
        super().__init__(f"decision is in terminal state {current.value!r}")
        self.current = current


@dataclass(frozen=True)
class DecisionEvent:
    """An audit event recorded against a decision.

    Attributes
    ----------
    decision_id:
        The decision this event belongs to.
    type:
        The kind of event.
    from_state / to_state:
        The state transitioned from and to. ``None`` for non-transition events.
    occurred_at:
        When the event was recorded.
    payload:
        Structured, non-sensitive details about the event.
    """

    decision_id: str
    type: DecisionEventType
    from_state: DecisionState | None = None
    to_state: DecisionState | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = field(default_factory=dict)


class DecisionLifecycle:
    """Tracks a single decision's state and audit trail.

    Parameters
    ----------
    decision_id:
        The decision identifier.
    initial_state:
        The starting state. Defaults to ``CREATED``; tests may start elsewhere.
    """

    def __init__(
        self,
        decision_id: str,
        *,
        initial_state: DecisionState = DecisionState.CREATED,
        occurred_at: datetime | None = None,
    ) -> None:
        if not decision_id:
            raise ValueError("decision_id must not be empty")
        self._decision_id = decision_id
        self._state = initial_state
        initial_event = DecisionEvent(
            decision_id=decision_id,
            type=DecisionEventType.CREATED,
            from_state=None,
            to_state=initial_state,
            occurred_at=occurred_at or datetime.now(UTC),
        )
        self._events: list[DecisionEvent] = [initial_event]

    @property
    def decision_id(self) -> str:
        return self._decision_id

    @property
    def state(self) -> DecisionState:
        return self._state

    @property
    def events(self) -> tuple[DecisionEvent, ...]:
        return tuple(self._events)

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def can_transition(self, target: DecisionState) -> bool:
        """Return whether ``target`` is reachable from the current state."""
        return target in ALLOWED_TRANSITIONS[self._state]

    def transition(
        self,
        target: DecisionState,
        *,
        event_type: DecisionEventType | None = None,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> DecisionEvent:
        """Move to ``target``, recording an audit event.

        Raises
        ------
        DecisionTerminalError
            If the decision is already in a terminal state.
        InvalidTransitionError
            If the transition is not allowed.
        """
        if self.is_terminal:
            raise DecisionTerminalError(self._state)
        if not self.can_transition(target):
            raise InvalidTransitionError(self._state, target)

        previous = self._state
        self._state = target
        event = DecisionEvent(
            decision_id=self._decision_id,
            type=event_type or _default_event_type(target),
            from_state=previous,
            to_state=target,
            occurred_at=occurred_at or datetime.now(UTC),
            payload=dict(payload or {}),
        )
        self._events.append(event)
        return event

    def record(
        self,
        event_type: DecisionEventType,
        *,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> DecisionEvent:
        """Record a non-transition audit event without changing state."""
        event = DecisionEvent(
            decision_id=self._decision_id,
            type=event_type,
            from_state=self._state,
            to_state=self._state,
            occurred_at=occurred_at or datetime.now(UTC),
            payload=dict(payload or {}),
        )
        self._events.append(event)
        return event

    # -- convenience transitions for the happy path -----------------------

    def start_evaluation(self, **payload: Any) -> DecisionEvent:
        return self.transition(DecisionState.EVALUATING, payload=payload)

    def complete_evaluation(self, **payload: Any) -> DecisionEvent:
        return self.transition(DecisionState.EVALUATED, payload=payload)

    def complete_policy_evaluation(self, **payload: Any) -> DecisionEvent:
        return self.transition(DecisionState.POLICY_EVALUATED, payload=payload)

    def select_action(self, **payload: Any) -> DecisionEvent:
        return self.transition(DecisionState.ACTION_SELECTED, payload=payload)

    def mark_executed(self, **payload: Any) -> DecisionEvent:
        return self.transition(DecisionState.EXECUTED, payload=payload)

    def record_outcome(self, **payload: Any) -> DecisionEvent:
        return self.transition(DecisionState.OUTCOME_RECORDED, payload=payload)

    def fail(self, **payload: Any) -> DecisionEvent:
        return self.transition(
            DecisionState.FAILED, event_type=DecisionEventType.FAILED, payload=payload
        )

    def expire(self, **payload: Any) -> DecisionEvent:
        return self.transition(
            DecisionState.EXPIRED, event_type=DecisionEventType.EXPIRED, payload=payload
        )

    def cancel(self, **payload: Any) -> DecisionEvent:
        return self.transition(
            DecisionState.CANCELLED, event_type=DecisionEventType.CANCELLED, payload=payload
        )


def _default_event_type(target: DecisionState) -> DecisionEventType:
    mapping = {
        DecisionState.EVALUATING: DecisionEventType.EVALUATION_STARTED,
        DecisionState.EVALUATED: DecisionEventType.EVALUATION_COMPLETED,
        DecisionState.POLICY_EVALUATED: DecisionEventType.POLICY_EVALUATED,
        DecisionState.ACTION_SELECTED: DecisionEventType.ACTION_SELECTED,
        DecisionState.EXECUTED: DecisionEventType.EXECUTED,
        DecisionState.OUTCOME_RECORDED: DecisionEventType.OUTCOME_RECORDED,
        DecisionState.FAILED: DecisionEventType.FAILED,
        DecisionState.EXPIRED: DecisionEventType.EXPIRED,
        DecisionState.CANCELLED: DecisionEventType.CANCELLED,
    }
    return mapping.get(target, DecisionEventType.STATE_TRANSITION)


__all__ = [
    "ALLOWED_TRANSITIONS",
    "FAILURE_STATES",
    "TERMINAL_STATES",
    "DecisionEvent",
    "DecisionLifecycle",
    "DecisionTerminalError",
    "InvalidTransitionError",
]
