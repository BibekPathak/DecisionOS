"""Raw, untrusted provider output.

A ``RawDecision`` is exactly what a provider returned, before DecisionOS has
validated it. It intentionally performs only light structural validation: the
authoritative probability/confidence/risk checks and the schema membership
check happen when a ``Decision`` is constructed from it.

Keeping raw output and validated decisions as distinct types makes the trust
boundary explicit: nothing downstream may consume a ``RawDecision`` as if it
were a ``Decision``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RawDecision(BaseModel):
    """Unvalidated decision output produced by a provider.

    Attributes
    ----------
    action:
        The provider's suggested action. May be ``None`` if the provider did
        not select one; it is checked against the schema later.
    confidence:
        Provider-reported confidence. May be ``None``.
    probabilities:
        Provider-reported distribution. May be empty or malformed.
    risk:
        Optional provider-reported risk. DecisionOS may instead derive risk.
    reason_codes:
        Optional provider-reported reason codes.
    provider:
        Name of the provider that produced this output.
    provider_request_id:
        Optional upstream request id, for tracing.
    latency_ms:
        Wall-clock time the provider call took, in milliseconds.
    raw_response:
        The unmodified provider response, retained for audit/debugging. This
        may contain provider-specific fields and must never be logged whole
        without redaction.
    """

    model_config = ConfigDict(extra="allow")

    action: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    risk: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    provider: str = Field(min_length=1)
    provider_request_id: str | None = None
    latency_ms: float = Field(ge=0.0)
    raw_response: dict[str, Any] = Field(default_factory=dict)


__all__ = ["RawDecision"]
