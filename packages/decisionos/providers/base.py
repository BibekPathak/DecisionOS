"""Provider abstraction.

A ``DecisionProvider`` turns a validated :class:`DecisionRequest` (and the
:class:`DecisionSchema` it targets) into a :class:`RawDecision` — a
probability distribution over the schema's actions, with confidence and an
optional reason set.

Providers are the *only* place probabilistic intelligence enters DecisionOS.
They never execute actions. All provider-specific behaviour (authentication,
retries, request formats) is confined to the provider implementation; the rest
of DecisionOS depends solely on this interface.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from decisionos.models import DecisionRequest, DecisionSchema, RawDecision


class ProviderError(Exception):
    """Base class for provider failures.

    Every provider error carries the provider name and an optional upstream
    request id so failures can be correlated without inspecting provider
    internals.
    """

    #: A short, machine-readable kind, used for metrics and audit events.
    kind: str = "provider_error"
    #: Whether the engine may retry the same request against this provider.
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.request_id = request_id


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached or is not configured."""

    kind = "unavailable"
    retryable = True


class ProviderTimeoutError(ProviderError):
    """The provider call exceeded its configured timeout."""

    kind = "timeout"
    retryable = True


class ProviderRateLimitError(ProviderError):
    """The provider rejected the call due to rate limiting (e.g. HTTP 429)."""

    kind = "rate_limit"
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        request_id: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider, request_id=request_id)
        self.retry_after_seconds = retry_after_seconds


class ProviderAuthError(ProviderError):
    """The provider rejected our credentials (e.g. HTTP 401/403)."""

    kind = "auth"
    retryable = False


class ProviderResponseError(ProviderError):
    """The provider returned a malformed or unusable response."""

    kind = "malformed_response"
    retryable = False


@runtime_checkable
class DecisionProvider(Protocol):
    """Structural interface every provider must satisfy.

    Implementations must be safe to call concurrently. They must not log
    secrets, authorization headers, or sensitive decision context.
    """

    #: Stable provider name used in decisions, metrics, and audit records.
    name: str

    async def evaluate(
        self,
        request: DecisionRequest,
        schema: DecisionSchema,
    ) -> RawDecision:
        """Evaluate ``request`` against ``schema`` and return raw output.

        Raises
        ------
        ProviderError
            A subclass of :class:`ProviderError` describing the failure. The
            engine maps these to typed API errors and metrics.
        """
        ...


__all__ = [
    "DecisionProvider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
]
