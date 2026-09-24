"""Deterministic in-process provider.

``MockProvider`` is mandatory infrastructure: it lets DecisionOS, its tests,
its demos, and its dashboard run to completion with no external credentials.

Behaviour is deterministic. A request is matched against the fixtures in
:mod:`decisionos.providers.fixtures`; if nothing matches, a valid distribution
is generated from a hash of the request so repeated calls return identical
output. The provider still respects the trust boundary — it produces a
:class:`RawDecision` and performs no decision-making beyond choosing
probabilities.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import Mapping
from typing import Any

from decisionos.models import DecisionRequest, DecisionSchema, RawDecision
from decisionos.providers.base import ProviderError
from decisionos.providers.fixtures import FIXTURES, MockFixture

# Simulated latency for the fallback path. Deterministic so dashboards and
# latency assertions are stable. Fixture hits report a fixed low latency.
_DEFAULT_LATENCY_MS = 4.0
_FIXTURE_LATENCY_MS = 84.0
_FALLBACK_PRECISION = 6


class MockProvider:
    """A deterministic provider backed by fixtures.

    Parameters
    ----------
    latency_ms:
        Simulated latency reported on the returned ``RawDecision``. When
        ``None`` a fixture-dependent default is used.
    fixtures:
        Optional fixture set override, primarily for tests.
    """

    name = "mock"

    def __init__(
        self,
        *,
        latency_ms: float | None = None,
        fixtures: tuple[MockFixture, ...] | None = None,
    ) -> None:
        self._latency_ms = latency_ms
        self._fixtures = fixtures if fixtures is not None else FIXTURES

    async def evaluate(
        self,
        request: DecisionRequest,
        schema: DecisionSchema,
    ) -> RawDecision:
        """Return a deterministic :class:`RawDecision` for ``request``.

        A zero-duration ``await`` yields control to the event loop so the mock
        behaves like any other async provider and does not block a request
        handler.
        """
        await asyncio.sleep(0)
        try:
            fixture = self._match_fixture(request, schema)
            if fixture is not None:
                return self._from_fixture(fixture, schema)
            return self._fallback(request, schema)
        except ProviderError:
            raise
        except Exception as error:  # pragma: no cover - defensive
            raise ProviderError(
                f"mock provider failed: {error}",
                provider=self.name,
            ) from error

    # -- internal helpers -------------------------------------------------

    def _match_fixture(
        self,
        request: DecisionRequest,
        schema: DecisionSchema,
    ) -> MockFixture | None:
        for fixture in self._fixtures:
            if fixture.schema_name is not None and fixture.schema_name != schema.name:
                continue
            if self._context_matches(request.context, fixture.match):
                return fixture
        return None

    @staticmethod
    def _context_matches(context: Mapping[str, Any], match: Mapping[str, object]) -> bool:
        if not match:
            return True
        for key, expected in match.items():
            if key not in context:
                return False
            actual = context[key]
            if isinstance(expected, bool):
                if bool(actual) is not expected:
                    return False
            elif actual != expected:
                return False
        return True

    def _from_fixture(self, fixture: MockFixture, schema: DecisionSchema) -> RawDecision:
        probabilities = _restrict_to_schema(fixture.probabilities, schema, fixture.action)
        latency = self._latency_ms if self._latency_ms is not None else _FIXTURE_LATENCY_MS
        return RawDecision(
            action=fixture.action,
            confidence=fixture.confidence,
            probabilities=probabilities,
            risk=fixture.risk,
            reason_codes=list(fixture.reason_codes),
            provider=self.name,
            latency_ms=latency,
            raw_response={"source": "fixture", "fixture_action": fixture.action},
        )

    def _fallback(self, request: DecisionRequest, schema: DecisionSchema) -> RawDecision:
        seed = _stable_seed(request, schema)
        rng = random.Random(seed)

        weights = {action: rng.random() + 0.01 for action in schema.actions}
        total = sum(weights.values())
        probabilities = {
            action: round(weight / total, _FALLBACK_PRECISION) for action, weight in weights.items()
        }
        probabilities = _renormalize(probabilities)

        action = max(probabilities, key=probabilities.__getitem__)
        confidence = probabilities[action]
        latency = self._latency_ms if self._latency_ms is not None else _DEFAULT_LATENCY_MS

        return RawDecision(
            action=action,
            confidence=confidence,
            probabilities=probabilities,
            risk=None,
            reason_codes=["mock_fallback"],
            provider=self.name,
            latency_ms=latency,
            raw_response={"source": "fallback", "seed": seed},
        )


def _stable_seed(request: DecisionRequest, schema: DecisionSchema) -> int:
    """Derive a deterministic integer seed from a request and schema."""
    payload = json.dumps(
        {
            "decision_type": request.decision_type,
            "schema": schema.key,
            "context": request.context,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _restrict_to_schema(
    probabilities: Mapping[str, float],
    schema: DecisionSchema,
    action: str,
) -> dict[str, float]:
    """Project fixture probabilities onto the schema's action set.

    Fixtures are written against a known action set; if a schema version drops
    an action, its probability mass is folded into the selected action so the
    distribution still sums to 1 and remains valid.
    """
    allowed = set(schema.actions)
    projected: dict[str, float] = {a: float(probabilities.get(a, 0.0)) for a in allowed}
    dropped = sum(value for a, value in probabilities.items() if a not in allowed)
    if dropped:
        target = action if action in projected else max(projected, key=projected.__getitem__)
        projected[target] += dropped
    return _renormalize(projected)


def _renormalize(probabilities: Mapping[str, float]) -> dict[str, float]:
    total = sum(probabilities.values())
    if total <= 0.0:  # pragma: no cover - guarded by callers
        raise ProviderError("cannot normalize an empty distribution", provider="mock")
    return {action: value / total for action, value in probabilities.items()}


__all__ = ["MockProvider"]
