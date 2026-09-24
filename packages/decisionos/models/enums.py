"""Enumerations shared across the DecisionOS domain model."""

from __future__ import annotations

from enum import StrEnum


class DecisionState(StrEnum):
    """Lifecycle states of a decision.

    The happy path is ordered; the failure states may be entered from any
    active state. Transitions are enforced by the lifecycle module.
    """

    CREATED = "created"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    POLICY_EVALUATED = "policy_evaluated"
    ACTION_SELECTED = "action_selected"
    EXECUTED = "executed"
    OUTCOME_RECORDED = "outcome_recorded"

    # Failure / terminal states.
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class DecisionEventType(StrEnum):
    """Types of audit events recorded against a decision."""

    CREATED = "created"
    EVALUATION_STARTED = "evaluation_started"
    EVALUATION_COMPLETED = "evaluation_completed"
    POLICY_EVALUATED = "policy_evaluated"
    ACTION_SELECTED = "action_selected"
    EXECUTED = "executed"
    OUTCOME_RECORDED = "outcome_recorded"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    STATE_TRANSITION = "state_transition"


class PolicyPrecedence(StrEnum):
    """Deterministic policy precedence, highest priority first.

    Model output can never bypass a higher-precedence rule.
    """

    HARD_DENY = "hard_deny"
    REQUIRED_HUMAN_REVIEW = "required_human_review"
    MODEL_DECISION = "model_decision"


__all__ = [
    "DecisionEventType",
    "DecisionState",
    "PolicyPrecedence",
]
