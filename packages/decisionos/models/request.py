"""The inbound decision request.

A ``DecisionRequest`` is the typed, validated input to the decision engine. It
names the schema the caller expects, carries the application context to be
evaluated, and optionally selects a provider, a policy, and an idempotency key.

DecisionOS deliberately separates the *schema* (the closed set of actions)
from the *context* (the facts to evaluate). Providers see only the context;
the policy engine sees the context and the resulting probabilities.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from decisionos.models.types import DEFAULT_MAX_CONTEXT_BYTES, context_size_bytes


class DecisionRequest(BaseModel):
    """A request to make a typed, probabilistic decision.

    Attributes
    ----------
    decision_type:
        Application-level category, e.g. ``"tool_authorization"``.
    schema_name / schema_version:
        The ``DecisionSchema`` this request is evaluated against.
    context:
        Structured facts to evaluate. Serialized size is bounded.
    metadata:
        Non-evaluated bookkeeping (correlation ids, caller, etc.).
    provider:
        Optional provider override; falls back to the configured default.
    policy:
        Optional policy name or ``name@version`` to evaluate against.
    idempotency_key:
        Optional caller-supplied key. Repeated requests with the same key must
        not create duplicate decisions.
    max_context_bytes:
        Per-request override of the maximum serialized context size.
    """

    model_config = ConfigDict(extra="forbid")

    decision_type: str = Field(min_length=1, max_length=128)
    schema_name: str = Field(min_length=1, max_length=128)
    schema_version: int = Field(ge=1)
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = Field(default=None, max_length=64)
    policy: str | None = Field(default=None, max_length=160)
    idempotency_key: str | None = Field(default=None, max_length=255)
    max_context_bytes: int | None = Field(default=None, gt=0)

    @field_validator("decision_type", "schema_name")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        if value != value.strip():
            raise ValueError("value must not contain leading or trailing whitespace")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def _validate_idempotency_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("idempotency_key must not be blank when provided")
        return value

    @field_validator("context")
    @classmethod
    def _validate_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("context must be an object")
        return value

    def context_size_bytes(self) -> int:
        """Return the serialized size of ``context`` in bytes."""
        return context_size_bytes(self.context)

    def effective_max_context_bytes(self) -> int:
        """Return the per-request or default maximum context size."""
        return self.max_context_bytes or DEFAULT_MAX_CONTEXT_BYTES

    def validate_context_size(self) -> None:
        """Raise ``ValueError`` if the context exceeds the allowed size."""
        size = self.context_size_bytes()
        limit = self.effective_max_context_bytes()
        if size > limit:
            raise ValueError(f"context is {size} bytes, exceeding the limit of {limit} bytes")

    @property
    def schema_key(self) -> str:
        """The ``name@version`` key of the requested schema."""
        return f"{self.schema_name}@{self.schema_version}"


__all__ = ["DecisionRequest"]
