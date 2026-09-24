"""The validated decision produced by DecisionOS.

A ``Decision`` is the trusted, normalized result of evaluating a
``DecisionRequest`` against a provider and (later) a policy. Unlike a
``RawDecision``, every field has been validated:

* ``0 <= confidence <= 1``
* ``0 <= risk <= 1``
* every probability is in ``[0, 1]``
* the probabilities sum to approximately 1
* ``action`` is either selected by the model or forced by policy

Construction from a ``RawDecision`` is the explicit trust boundary, via
``Decision.from_raw``. Never trust provider output without going through it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from decisionos.models.raw import RawDecision
from decisionos.models.schema import DecisionSchema
from decisionos.models.types import (
    PROBABILITY_EPSILON,
    PROBABILITY_MAX,
    PROBABILITY_MIN,
    PROBABILITY_SUM_TOLERANCE,
)


class ProviderOutputError(ValueError):
    """Raised when a provider's output cannot be trusted as a decision."""


class Decision(BaseModel):
    """A validated, typed decision with a probability distribution.

    Attributes
    ----------
    id:
        Stable decision identifier.
    decision_type / schema_name / schema_version:
        Which decision type and schema version this resolved against.
    action:
        The selected action. At construction this is the schema-validated
        provider action; policy may later override it (recorded separately).
    confidence:
        Confidence in the selected action, in ``[0, 1]``.
    probabilities:
        Distribution over the schema's actions, summing to approximately 1.
    risk:
        Optional risk estimate in ``[0, 1]``. Derived by DecisionOS when the
        provider does not supply one.
    reason_codes:
        Human-readable codes explaining the decision. Never fabricated by a
        model; sourced from the schema, policy rules, or provider metadata.
    provider / provider_request_id:
        Provenance of the probabilistic output.
    latency_ms:
        End-to-end provider evaluation latency.
    created_at:
        When the decision was created.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    schema_name: str = Field(min_length=1)
    schema_version: int = Field(ge=1)

    action: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float] = Field(default_factory=dict)
    risk: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)

    provider: str = Field(min_length=1)
    provider_request_id: str | None = None
    latency_ms: float = Field(ge=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("probabilities")
    @classmethod
    def _validate_probabilities(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("probabilities must not be empty")
        for name, probability in value.items():
            if not isinstance(probability, (int, float)):
                raise ValueError(f"probability for {name!r} is not numeric")
            if probability < PROBABILITY_MIN - PROBABILITY_EPSILON:
                raise ValueError(f"probability for {name!r} is negative: {probability}")
            if probability > PROBABILITY_MAX + PROBABILITY_EPSILON:
                raise ValueError(f"probability for {name!r} exceeds 1: {probability}")
        return value

    @model_validator(mode="after")
    def _validate_distribution(self) -> Decision:
        total = sum(self.probabilities.values())
        if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
            raise ValueError(f"probabilities sum to {total!r}, which is not approximately 1")
        if self.action not in self.probabilities:
            raise ValueError(f"selected action {self.action!r} is not present in probabilities")
        return self

    @classmethod
    def from_raw(
        cls,
        raw: RawDecision,
        *,
        decision_id: str,
        decision_type: str,
        schema: DecisionSchema,
        context: dict[str, Any] | None = None,
    ) -> Decision:
        """Build a validated ``Decision`` from untrusted provider output.

        Raises
        ------
        ProviderOutputError
            If the provider output is missing required fields, names an action
            outside the schema, or carries an invalid probability
            distribution.
        """
        del context  # reserved for provenance; not part of the decision body

        if not raw.action:
            raise ProviderOutputError("provider did not return an action")
        if raw.action not in schema.actions:
            raise ProviderOutputError(
                f"provider returned action {raw.action!r} not in schema {schema.key}"
            )
        if not raw.probabilities:
            raise ProviderOutputError("provider did not return probabilities")

        normalized = _normalize_probabilities(raw.probabilities)
        confidence = raw.confidence
        if confidence is None:
            confidence = normalized.get(raw.action, 0.0)
        if not (
            PROBABILITY_MIN - PROBABILITY_EPSILON
            <= confidence
            <= PROBABILITY_MAX + PROBABILITY_EPSILON
        ):
            raise ProviderOutputError(f"provider confidence out of range: {confidence}")

        risk = raw.risk
        if risk is None:
            risk = _derive_risk(normalized, raw.action)
        if risk is not None and not (
            PROBABILITY_MIN - PROBABILITY_EPSILON <= risk <= PROBABILITY_MAX + PROBABILITY_EPSILON
        ):
            raise ProviderOutputError(f"provider risk out of range: {risk}")

        try:
            return cls(
                id=decision_id,
                decision_type=decision_type,
                schema_name=schema.name,
                schema_version=schema.version,
                action=raw.action,
                confidence=min(max(confidence, 0.0), 1.0),
                probabilities=normalized,
                risk=None if risk is None else min(max(risk, 0.0), 1.0),
                reason_codes=list(dict.fromkeys(raw.reason_codes)),
                provider=raw.provider,
                provider_request_id=raw.provider_request_id,
                latency_ms=raw.latency_ms,
            )
        except ValueError as error:  # pragma: no cover - defensive re-wrap
            raise ProviderOutputError(str(error)) from error

    @property
    def schema_key(self) -> str:
        """The ``name@version`` key of the schema this decision used."""
        return f"{self.schema_name}@{self.schema_version}"

    def with_action(
        self,
        action: str,
        *,
        reason_codes: list[str] | None = None,
    ) -> Decision:
        """Return a copy with ``action`` replaced (used by the policy engine).

        The probability distribution is preserved unchanged: policy overrides
        the *decision*, not the model's estimate of the world.
        """
        return self.model_copy(
            update={
                "action": action,
                "reason_codes": reason_codes if reason_codes is not None else self.reason_codes,
            }
        )


def _normalize_probabilities(probabilities: dict[str, float]) -> dict[str, float]:
    """Validate and renormalize a probability distribution.

    Values are clamped for tiny floating-point excursions, then the distribution
    is renormalized to sum exactly to 1. Genuinely malformed distributions
    (negative values, values well above 1, or a non-positive total) raise
    ``ProviderOutputError``.
    """
    if not probabilities:
        raise ProviderOutputError("probabilities must not be empty")

    cleaned: dict[str, float] = {}
    for name, probability in probabilities.items():
        if not isinstance(probability, (int, float)) or isinstance(probability, bool):
            raise ProviderOutputError(f"probability for {name!r} is not numeric")
        if probability < PROBABILITY_MIN - PROBABILITY_EPSILON:
            raise ProviderOutputError(f"probability for {name!r} is negative: {probability}")
        if probability > PROBABILITY_MAX + PROBABILITY_EPSILON:
            raise ProviderOutputError(f"probability for {name!r} exceeds 1: {probability}")
        cleaned[name] = min(max(float(probability), 0.0), 1.0)

    total = sum(cleaned.values())
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
        raise ProviderOutputError(f"probabilities sum to {total!r}, which is not approximately 1")
    if total <= 0.0:  # pragma: no cover - unreachable given the sum check
        raise ProviderOutputError("probability distribution has zero mass")

    scale = 1.0 / total
    return {name: value * scale for name, value in cleaned.items()}


def _derive_risk(probabilities: dict[str, float], chosen_action: str) -> float:
    """Derive a risk estimate from the distribution when none is supplied.

    DecisionOS has no native notion of which actions are "safe", so risk is
    defined as the model's uncertainty: ``1 - P[chosen_action]``. A confident
    decision is low-risk; a diffuse distribution is high-risk. This is the
    ``risk = 1 - confidence-like`` signal, computed from the distribution
    rather than from provider-supplied confidence.
    """
    return min(max(1.0 - probabilities.get(chosen_action, 0.0), 0.0), 1.0)


__all__ = ["Decision", "ProviderOutputError"]
