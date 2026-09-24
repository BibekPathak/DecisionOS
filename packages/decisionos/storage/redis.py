"""Redis-backed coordination: idempotency, caching, and rate limiting.

Redis is used for short-lived, cross-process coordination. Each concern is
isolated behind a small class so the rest of DecisionOS does not depend on the
Redis client directly and so tests can substitute an in-memory backend.

A :class:`RedisBackend` may be built from a URL. If Redis is unreachable, the
caller can fall back to :class:`InMemoryBackend`; this keeps DecisionOS running
(without cross-process guarantees) when Redis is unavailable.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from decisionos.config import Settings, get_settings
from decisionos.observability.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class KeyValueBackend(Protocol):
    """Minimal asynchronous key/value contract used by the stores."""

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set ``key`` only if absent. Returns True when the key was set."""
        ...

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        """Atomically increment a counter, setting a TTL on first write."""
        ...

    async def close(self) -> None: ...


class InMemoryBackend:
    """A process-local key/value backend.

    Used in tests and as a fallback when Redis is unavailable. It provides no
    cross-process guarantees.
    """

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float | None]] = {}

    def _now(self) -> float:
        return time.monotonic()

    def _expired(self, key: str) -> bool:
        entry = self._values.get(key)
        if entry is None:
            return True
        _, expires_at = entry
        if expires_at is not None and expires_at <= self._now():
            self._values.pop(key, None)
            return True
        return False

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool:
        if not self._expired(key):
            return False
        expires_at = self._now() + ttl_seconds if ttl_seconds > 0 else None
        self._values[key] = (value, expires_at)
        return True

    async def get(self, key: str) -> str | None:
        if self._expired(key):
            return None
        return self._values[key][0]

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = self._now() + ttl_seconds if ttl_seconds > 0 else None
        self._values[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._values.pop(key, None)

    async def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        if self._expired(key):
            expires_at = self._now() + ttl_seconds if ttl_seconds > 0 else None
            self._values[key] = ("1", expires_at)
            return 1
        current = int(self._values[key][0]) + 1
        self._values[key] = (str(current), self._values[key][1])
        return current

    async def close(self) -> None:
        self._values.clear()


class RedisBackend:
    """A ``redis.asyncio`` backed key/value store."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url, decode_responses=True)

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool:
        result = await self._redis.set(key, value, nx=True, ex=ttl_seconds or None)
        return bool(result)

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._redis.set(key, value, ex=ttl_seconds or None)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            if ttl_seconds > 0:
                pipe.expire(key, ttl_seconds, nx=True)
            result = await pipe.execute()
        return int(result[0])

    async def close(self) -> None:
        await self._redis.aclose()


def build_backend(settings: Settings | None = None) -> KeyValueBackend:
    """Build a Redis backend, falling back to in-memory on connection errors.

    The fallback is logged at warning level because it removes cross-process
    idempotency guarantees.
    """
    settings = settings or get_settings()
    try:
        return RedisBackend(settings.redis_url)
    except Exception as error:  # pragma: no cover - depends on environment
        logger.warning(
            "redis.unavailable_using_memory_backend",
            error=str(error),
        )
        return InMemoryBackend()


class IdempotencyStore:
    """Coordinates idempotent decision creation.

    A request reserves its key before work begins. The winner stores the
    resulting decision id; concurrent callers observe the reservation and wait
    for (or read back) the stored decision id.
    """

    def __init__(self, backend: KeyValueBackend, *, ttl_seconds: int = 60 * 60 * 24) -> None:
        self._backend = backend
        self._ttl = ttl_seconds

    @staticmethod
    def _key(idempotency_key: str) -> str:
        return f"decisionos:idempotency:{idempotency_key}"

    async def reserve(self, idempotency_key: str) -> bool:
        """Claim the key. Returns True if this caller won the reservation."""
        return await self._backend.set_nx(self._key(idempotency_key), "pending", self._ttl)

    async def complete(self, idempotency_key: str, decision_id: str) -> None:
        """Record the decision id for a reserved key."""
        await self._backend.set(self._key(idempotency_key), decision_id, self._ttl)

    async def get(self, idempotency_key: str) -> str | None:
        """Return the stored decision id, or ``None`` if absent or pending."""
        value = await self._backend.get(self._key(idempotency_key))
        if value in (None, "pending"):
            return None
        return value

    async def release(self, idempotency_key: str) -> None:
        """Release a reservation (on failure, so the caller may retry)."""
        await self._backend.delete(self._key(idempotency_key))


class Cache:
    """A small JSON cache for immutable schemas and policies."""

    def __init__(self, backend: KeyValueBackend, *, ttl_seconds: int = 300) -> None:
        self._backend = backend
        self._ttl = ttl_seconds

    async def get_json(self, key: str) -> Any | None:
        import json

        raw = await self._backend.get(f"decisionos:cache:{key}")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:  # pragma: no cover - corrupted entry
            await self._backend.delete(f"decisionos:cache:{key}")
            return None

    async def set_json(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        import json

        await self._backend.set(
            f"decisionos:cache:{key}",
            json.dumps(value, default=str),
            ttl_seconds or self._ttl,
        )


class RateLimiter:
    """A fixed-window rate limiter.

    Returns a result describing whether the request is allowed, the remaining
    allowance, and how long until the window resets.
    """

    def __init__(self, backend: KeyValueBackend, *, limit: int, window_seconds: int = 60) -> None:
        self._backend = backend
        self._limit = limit
        self._window = window_seconds

    async def check(self, identifier: str) -> RateLimitResult:
        if self._limit <= 0:
            return RateLimitResult(allowed=True, remaining=self._limit, retry_after_seconds=0)
        key = f"decisionos:ratelimit:{identifier}"
        count = await self._backend.incr_with_ttl(key, self._window)
        remaining = max(self._limit - count, 0)
        allowed = count <= self._limit
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            retry_after_seconds=self._window if not allowed else 0,
        )


class RateLimitResult:
    """The outcome of a rate-limit check."""

    def __init__(self, *, allowed: bool, remaining: int, retry_after_seconds: int) -> None:
        self.allowed = allowed
        self.remaining = remaining
        self.retry_after_seconds = retry_after_seconds


__all__ = [
    "Cache",
    "IdempotencyStore",
    "InMemoryBackend",
    "KeyValueBackend",
    "RateLimitResult",
    "RateLimiter",
    "RedisBackend",
    "build_backend",
]
