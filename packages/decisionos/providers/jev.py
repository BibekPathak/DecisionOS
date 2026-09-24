"""Jev (TypeSafe) provider.

Jev is DecisionOS's primary probabilistic provider. All Jev-specific behaviour
lives in this module; the rest of DecisionOS depends only on the
:class:`~decisionos.providers.base.DecisionProvider` interface.

Verified TypeSafe System One API surface (see the official docs):

* endpoint: ``POST {base_url}/v1/systemone``
* auth: ``Authorization: Bearer <API_KEY>``
* request body::

      {
        "state": <string | object | array>,
        "model": "jev-latest",
        "questions": {
          "<id>": {
            "type": "choice",
            "instructions": <string | object | array>,
            "criteria": {"<option>": <string | object | array | null>, ...}
          }
        }
      }

* response body::

      {
        "model": "jev-1.13.0",
        "answers": {
          "<id>": {
            "type": "choice",
            "choice": "<option>",
            "probabilities": {"<option>": <float>, ...},
            "confidence": <float>
          }
        },
        "usage": {"input_tokens": <int>, "output_tokens": <int>}
      }

* errors: ``401`` (auth), ``422`` (validation), ``429`` (rate limit), ``529``
  (overloaded); the ``x-typesafe-request-id`` response header carries the
  upstream request id and ``retry-after`` may accompany ``429``.

Jev's primitives are Choice, Score, and Noul. DecisionOS maps a schema's
actions to a single Choice question whose ``criteria`` are the actions, then
treats the returned ``choice``/``probabilities``/``confidence`` as the raw
decision. The response is returned as an untrusted :class:`RawDecision`; the
engine validates it at the trust boundary.

If Jev is not configured (no API key), :func:`build_jev_provider` raises so the
registry falls back to the mock provider and DecisionOS keeps running.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx

from decisionos.config import Settings
from decisionos.models import DecisionRequest, DecisionSchema, RawDecision
from decisionos.observability.logging import get_logger
from decisionos.providers.base import (
    DecisionProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = get_logger(__name__)

# The question id under which the action choice is sent and read back. TypeSafe
# never sees this id; it only keys the response.
_ACTION_QUESTION_ID = "action"

# HTTP statuses that warrant a retry, beyond the specific 429/529 handling.
_RETRYABLE_STATUS = frozenset({500, 502, 503, 504, 529})


class JevProvider:
    """Provider backed by the TypeSafe System One API.

    Parameters
    ----------
    api_key:
        TypeSafe API key. Never logged.
    base_url:
        API root, e.g. ``https://api.typesafe.ai``.
    model:
        Model name or alias, e.g. ``jev-latest``.
    timeout_seconds:
        Per-request timeout.
    max_retries:
        Maximum retry attempts after the first try.
    backoff_base_seconds / backoff_max_seconds:
        Exponential backoff bounds; a ``retry-after`` header overrides backoff.
    transport:
        Optional httpx transport, primarily for tests.
    """

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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds
        # A single client reuses connections across calls. Tests may inject a
        # transport (e.g. httpx.MockTransport) to avoid real network access.
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client and its connection pool."""
        await self._client.aclose()

    async def evaluate(
        self,
        request: DecisionRequest,
        schema: DecisionSchema,
    ) -> RawDecision:
        """Evaluate ``request`` via Jev and return an untrusted ``RawDecision``.

        Raises
        ------
        ProviderAuthError, ProviderRateLimitError, ProviderTimeoutError,
        ProviderUnavailableError, ProviderResponseError
            Subclasses of :class:`ProviderError` describing the failure.
        """
        payload = self._build_payload(request, schema)

        started = time.perf_counter()
        response = await self._request_with_retries(payload)
        latency_ms = (time.perf_counter() - started) * 1000.0

        request_id = response.headers.get("x-typesafe-request-id")
        body = self._decode_json(response, request_id=request_id)
        return self._parse_answer(
            body,
            schema=schema,
            latency_ms=latency_ms,
            request_id=request_id,
        )

    # -- request construction --------------------------------------------

    def _build_payload(self, request: DecisionRequest, schema: DecisionSchema) -> dict[str, Any]:
        return {
            "state": {
                "decision_type": request.decision_type,
                "schema": {"name": schema.name, "version": schema.version},
                "context": request.context,
            },
            "model": self._model,
            "questions": {
                _ACTION_QUESTION_ID: {
                    "type": "choice",
                    "instructions": (
                        f"Decide the correct action for this {request.decision_type} "
                        "decision. Choose the single best action for the given context."
                    ),
                    "criteria": schema.jev_criteria(),
                }
            },
        }

    # -- transport, retries, and error mapping ---------------------------

    async def _request_with_retries(self, payload: dict[str, Any]) -> httpx.Response:
        attempt = 0
        last_error: ProviderError | None = None

        while attempt <= self._max_retries:
            try:
                response = await self._client.post("/v1/systemone", json=payload)
            except httpx.TimeoutException as error:
                last_error = ProviderTimeoutError(
                    f"Jev request timed out after {self._timeout_seconds}s",
                    provider=self.name,
                )
                logger.warning(
                    "jev.request_timeout",
                    attempt=attempt,
                    model=self._model,
                    error_type=type(error).__name__,
                )
            except httpx.HTTPError as error:
                last_error = ProviderUnavailableError(
                    "Jev is unreachable",
                    provider=self.name,
                )
                logger.warning(
                    "jev.request_network_error",
                    attempt=attempt,
                    model=self._model,
                    error_type=type(error).__name__,
                )
            else:
                if response.status_code < 400:
                    return response
                last_error = self._error_for_response(response)

            if not last_error.retryable or attempt >= self._max_retries:
                break

            delay = self._backoff_delay(attempt, last_error)
            logger.info(
                "jev.retrying",
                attempt=attempt,
                delay_seconds=round(delay, 3),
                kind=last_error.kind,
                model=self._model,
            )
            await asyncio.sleep(delay)
            attempt += 1

        assert last_error is not None  # the loop always sets it before breaking
        raise last_error

    def _error_for_response(self, response: httpx.Response) -> ProviderError:
        status = response.status_code
        request_id = response.headers.get("x-typesafe-request-id")

        if status in (401, 403):
            # Never include the response body: it may echo request content.
            return ProviderAuthError(
                f"Jev authentication failed (HTTP {status})",
                provider=self.name,
                request_id=request_id,
            )
        if status == 429:
            return ProviderRateLimitError(
                "Jev rate limit exceeded (HTTP 429)",
                provider=self.name,
                request_id=request_id,
                retry_after_seconds=_parse_retry_after(response.headers.get("retry-after")),
            )
        if status == 422:
            return ProviderResponseError(
                "Jev rejected the request as invalid (HTTP 422)",
                provider=self.name,
                request_id=request_id,
            )
        if status in _RETRYABLE_STATUS:
            return ProviderUnavailableError(
                f"Jev is temporarily unavailable (HTTP {status})",
                provider=self.name,
                request_id=request_id,
            )
        return ProviderResponseError(
            f"Jev returned an unexpected status (HTTP {status})",
            provider=self.name,
            request_id=request_id,
        )

    def _backoff_delay(self, attempt: int, error: ProviderError) -> float:
        if isinstance(error, ProviderRateLimitError) and error.retry_after_seconds:
            return min(error.retry_after_seconds, self._backoff_max_seconds)
        # Exponential backoff with full jitter, bounded by the max.
        ceiling = min(self._backoff_base_seconds * (2**attempt), self._backoff_max_seconds)
        return random.uniform(0.0, ceiling)

    # -- response parsing ------------------------------------------------

    @staticmethod
    def _decode_json(response: httpx.Response, *, request_id: str | None) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as error:
            raise ProviderResponseError(
                "Jev returned a non-JSON response",
                provider="jev",
                request_id=request_id,
            ) from error
        if not isinstance(body, dict):
            raise ProviderResponseError(
                "Jev response was not a JSON object",
                provider="jev",
                request_id=request_id,
            )
        return body

    def _parse_answer(
        self,
        body: dict[str, Any],
        *,
        schema: DecisionSchema,
        latency_ms: float,
        request_id: str | None,
    ) -> RawDecision:
        answers = body.get("answers")
        if not isinstance(answers, dict):
            raise ProviderResponseError(
                "Jev response is missing the 'answers' object",
                provider=self.name,
                request_id=request_id,
            )
        answer = answers.get(_ACTION_QUESTION_ID)
        if not isinstance(answer, dict):
            raise ProviderResponseError(
                f"Jev response is missing the {_ACTION_QUESTION_ID!r} answer",
                provider=self.name,
                request_id=request_id,
            )

        choice = answer.get("choice")
        probabilities = answer.get("probabilities")
        confidence = answer.get("confidence")
        if not isinstance(choice, str) or not choice:
            raise ProviderResponseError(
                "Jev answer is missing a 'choice'",
                provider=self.name,
                request_id=request_id,
            )
        if not isinstance(probabilities, dict):
            raise ProviderResponseError(
                "Jev answer is missing 'probabilities'",
                provider=self.name,
                request_id=request_id,
            )

        parsed_probabilities: dict[str, float] = {}
        for option, value in probabilities.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ProviderResponseError(
                    f"Jev returned a non-numeric probability for {option!r}",
                    provider=self.name,
                    request_id=request_id,
                )
            parsed_probabilities[str(option)] = float(value)

        parsed_confidence = float(confidence) if isinstance(confidence, (int, float)) else None

        reason_codes = [f"model:{body.get('model')}"] if body.get("model") else []

        return RawDecision(
            action=choice,
            confidence=parsed_confidence,
            probabilities=parsed_probabilities,
            risk=None,
            reason_codes=reason_codes,
            provider=self.name,
            provider_request_id=request_id,
            latency_ms=latency_ms,
            raw_response={
                "model": body.get("model"),
                "usage": body.get("usage", {}),
                # The unmodified answer, for audit. Never contains secrets.
                "answer": answer,
            },
        )


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``retry-after`` header value in seconds, if present."""
    if not value:
        return None
    try:
        return max(float(value.strip()), 0.0)
    except ValueError:
        # The header may be an HTTP-date; we do not attempt to parse it here.
        return None


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
