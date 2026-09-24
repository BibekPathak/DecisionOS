"""Jev (TypeSafe) provider.

Jev is DecisionOS's primary probabilistic provider. All Jev-specific behaviour
lives in this module; the rest of DecisionOS depends only on the
:class:`~decisionos.providers.base.DecisionProvider` interface.

This module currently provides the provider *shell*: configuration handling
and the trust-boundary plumbing. The HTTP call to TypeSafe's
``POST /v1/systemone`` endpoint, retry/backoff, and response parsing are
implemented in Phase 7, against the verified TypeSafe API:

* endpoint: ``POST {JEV_BASE_URL}/v1/systemone``
* auth: ``Authorization: Bearer <JEV_API_KEY>``
* request: ``{state, model, questions: {<id>: {type: "choice", instructions, criteria}}}``
* response: ``{model, answers: {<id>: {type, choice, probabilities, confidence}}, usage}``
* errors: 401/422/429/529, with ``x-typesafe-request-id`` and ``retry-after``

The TypeSafe primitives are Choice, Score, and Noul. DecisionOS maps a
schema's actions to a single Choice question whose ``criteria`` are the
actions, then treats the returned ``choice``/``probabilities``/``confidence``
as the raw decision.

If Jev is not configured (no API key), :func:`build_jev_provider` raises so the
registry falls back to the mock provider and DecisionOS keeps running.
"""

from __future__ import annotations

from decisionos.config import Settings
from decisionos.models import DecisionRequest, DecisionSchema, RawDecision
from decisionos.providers.base import DecisionProvider, ProviderUnavailableError


class JevProvider:
    """Provider backed by the TypeSafe System One API."""

    name = "jev"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
        backoff_max_seconds: float = 8.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds

    async def evaluate(
        self,
        request: DecisionRequest,
        schema: DecisionSchema,
    ) -> RawDecision:
        """Evaluate ``request`` via Jev. Implemented in Phase 7."""
        raise ProviderUnavailableError(
            "Jev provider is not yet implemented; use the mock provider",
            provider=self.name,
        )


def build_jev_provider(settings: Settings) -> DecisionProvider:
    """Build a :class:`JevProvider` from settings.

    Raises
    ------
    ProviderUnavailableError
        When no API key is configured. The registry treats a factory failure as
        a reason to fall back to the mock provider.
    """
    api_key = settings.jev_api_key.get_secret_value().strip()
    if not api_key:
        raise ProviderUnavailableError(
            "JEV_API_KEY is not configured",
            provider="jev",
        )
    return JevProvider(
        api_key=api_key,
        base_url=settings.jev_base_url,
        model=settings.jev_model,
        timeout_seconds=settings.jev_timeout_seconds,
        max_retries=settings.jev_max_retries,
        backoff_base_seconds=settings.jev_backoff_base_seconds,
        backoff_max_seconds=settings.jev_backoff_max_seconds,
    )


__all__ = ["JevProvider", "build_jev_provider"]
