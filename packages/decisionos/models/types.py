"""Shared types, constants, and validation helpers for the domain model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Absolute tolerance used when checking that a probability distribution sums
# to 1.0. Providers serialize floats, so exact equality is not reliable; a
# total deviation of 1e-6 is well within serialization noise while still
# rejecting genuinely malformed distributions.
PROBABILITY_SUM_TOLERANCE = 1e-6

# Default maximum size (in bytes) of a serialized decision ``context``.
DEFAULT_MAX_CONTEXT_BYTES = 64 * 1024

# Probability values outside this range are rejected. A tiny margin above 1.0
# tolerates float rounding in provider output before the sum check runs.
PROBABILITY_MIN = 0.0
PROBABILITY_MAX = 1.0
PROBABILITY_EPSILON = 1e-6


def context_size_bytes(context: Mapping[str, Any]) -> int:
    """Return the UTF-8 encoded size of a JSON-serialized context.

    Uses compact JSON (no whitespace) so the measurement reflects the
    minimum wire size. Non-serializable values raise ``TypeError``.
    """
    import json

    return len(json.dumps(context, separators=(",", ":"), default=str).encode("utf-8"))


__all__ = [
    "DEFAULT_MAX_CONTEXT_BYTES",
    "PROBABILITY_EPSILON",
    "PROBABILITY_MAX",
    "PROBABILITY_MIN",
    "PROBABILITY_SUM_TOLERANCE",
    "context_size_bytes",
]
