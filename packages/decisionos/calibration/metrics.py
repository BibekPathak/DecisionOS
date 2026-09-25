"""Calibration metrics.

Every decision stores a predicted probability (its confidence in the selected
action) and, once observed, an outcome. Calibration measures how well those
predicted probabilities match reality.

Definitions used here are the standard ones:

* **Brier score** — the mean squared error between predicted probability and
  the binary outcome: ``mean((p - y) ** 2)``. Lower is better; ``0`` is perfect.
* **Reliability buckets** — samples grouped by predicted probability into
  fixed-width bins; each bin reports its count, its observed accuracy
  (fraction of ``y == 1``), and its mean predicted probability.
* **Expected Calibration Error (ECE)** — the count-weighted mean absolute gap
  between a bucket's mean predicted probability and its observed accuracy.

For a decision, the predicted probability is the model's confidence in the
action it selected, and the outcome ``y`` is ``1`` when that decision was
recorded as successful.

All functions are pure and take plain ``CalibrationSample`` values so they can
be tested independently of storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CalibrationSample:
    """A single predicted-probability / observed-outcome pair.

    Attributes
    ----------
    predicted:
        The predicted probability that the chosen action was correct, in
        ``[0, 1]``.
    outcome:
        ``1`` when the decision was correct/successful, else ``0``.
    """

    predicted: float
    outcome: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.predicted <= 1.0:
            raise ValueError(f"predicted probability out of range: {self.predicted}")
        if self.outcome not in (0, 1):
            raise ValueError(f"outcome must be 0 or 1, got {self.outcome!r}")


@dataclass(frozen=True)
class ReliabilityBucket:
    """Observed calibration within a probability interval ``[lower, upper)``."""

    lower: float
    upper: float
    count: int
    accuracy: float
    avg_confidence: float


@dataclass(frozen=True)
class CalibrationReport:
    """The computed calibration of a set of samples."""

    sample_count: int
    brier_score: float | None = None
    expected_calibration_error: float | None = None
    buckets: list[ReliabilityBucket] = field(default_factory=list)


def brier_score(samples: list[CalibrationSample]) -> float | None:
    """Return the Brier score for ``samples``, or ``None`` if empty."""
    if not samples:
        return None
    total = sum((sample.predicted - sample.outcome) ** 2 for sample in samples)
    return total / len(samples)


def reliability_buckets(
    samples: list[CalibrationSample],
    *,
    n_buckets: int = 10,
) -> list[ReliabilityBucket]:
    """Group ``samples`` into ``n_buckets`` equal-width probability bins.

    Bins span ``[0, 1]``. A prediction of exactly ``1.0`` falls into the last
    bin. Empty bins are omitted from the result (they carry no information and
    would make ECE weighting meaningless).
    """
    if n_buckets < 1:
        raise ValueError("n_buckets must be at least 1")
    if not samples:
        return []

    width = 1.0 / n_buckets
    counts = [0] * n_buckets
    outcome_sums = [0] * n_buckets
    predicted_sums = [0.0] * n_buckets

    for sample in samples:
        index = _bucket_index(sample.predicted, width, n_buckets)
        counts[index] += 1
        outcome_sums[index] += sample.outcome
        predicted_sums[index] += sample.predicted

    buckets: list[ReliabilityBucket] = []
    for index, count in enumerate(counts):
        if count == 0:
            continue
        lower = index * width
        upper = lower + width
        buckets.append(
            ReliabilityBucket(
                lower=lower,
                upper=upper,
                count=count,
                accuracy=outcome_sums[index] / count,
                avg_confidence=predicted_sums[index] / count,
            )
        )
    return buckets


def expected_calibration_error(
    samples: list[CalibrationSample],
    *,
    n_buckets: int = 10,
) -> float | None:
    """Return the expected calibration error for ``samples``, or ``None``."""
    if not samples:
        return None
    buckets = reliability_buckets(samples, n_buckets=n_buckets)
    total = len(samples)
    return sum(
        (bucket.count / total) * abs(bucket.accuracy - bucket.avg_confidence) for bucket in buckets
    )


def compute_report(
    samples: list[CalibrationSample],
    *,
    n_buckets: int = 10,
) -> CalibrationReport:
    """Compute the full calibration report for ``samples``."""
    if not samples:
        return CalibrationReport(sample_count=0)
    return CalibrationReport(
        sample_count=len(samples),
        brier_score=brier_score(samples),
        expected_calibration_error=expected_calibration_error(samples, n_buckets=n_buckets),
        buckets=reliability_buckets(samples, n_buckets=n_buckets),
    )


def _bucket_index(predicted: float, width: float, n_buckets: int) -> int:
    if predicted >= 1.0:
        return n_buckets - 1
    index = int(predicted / width)
    return min(max(index, 0), n_buckets - 1)


__all__ = [
    "CalibrationReport",
    "CalibrationSample",
    "ReliabilityBucket",
    "brier_score",
    "compute_report",
    "expected_calibration_error",
    "reliability_buckets",
]
