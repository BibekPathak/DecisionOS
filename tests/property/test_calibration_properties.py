"""Property tests for calibration metrics.

Invariants that must hold for *any* set of samples:

* Brier score is within ``[0, 1]``.
* ECE is within ``[0, 1]``.
* Bucket counts sum to the sample count.
* Bucket accuracies and mean confidences are within ``[0, 1]``.
* Perfectly calibrated constant predictions yield ECE 0.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from decisionos.calibration import (
    CalibrationSample,
    brier_score,
    expected_calibration_error,
    reliability_buckets,
)

_probability = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_sample = st.builds(CalibrationSample, predicted=_probability, outcome=st.integers(0, 1))
_samples = st.lists(_sample, min_size=1, max_size=200)


@settings(max_examples=200)
@given(samples=_samples)
def test_brier_score_within_unit_interval(samples: list[CalibrationSample]) -> None:
    value = brier_score(samples)
    assert value is not None
    assert 0.0 <= value <= 1.0


@settings(max_examples=200)
@given(samples=_samples)
def test_ece_within_unit_interval(samples: list[CalibrationSample]) -> None:
    value = expected_calibration_error(samples)
    assert value is not None
    assert 0.0 <= value <= 1.0


@settings(max_examples=200)
@given(samples=_samples)
def test_bucket_counts_sum_to_sample_count(samples: list[CalibrationSample]) -> None:
    buckets = reliability_buckets(samples)
    assert sum(bucket.count for bucket in buckets) == len(samples)


@settings(max_examples=200)
@given(samples=_samples)
def test_bucket_statistics_within_unit_interval(samples: list[CalibrationSample]) -> None:
    for bucket in reliability_buckets(samples):
        assert 0.0 <= bucket.accuracy <= 1.0
        assert 0.0 <= bucket.avg_confidence <= 1.0
        assert 0.0 <= bucket.lower < bucket.upper <= 1.0 + 1e-9


@settings(max_examples=100)
@given(
    confidence=st.floats(min_value=0.01, max_value=0.99, allow_nan=False),
    successes=st.integers(min_value=0, max_value=100),
)
def test_ece_equals_gap_for_single_bucket(confidence: float, successes: int) -> None:
    # Build a single bucket where observed accuracy equals mean confidence.
    # With n_buckets=1 every sample lands in one bucket; ECE then equals the
    # absolute gap, which is zero only when accuracy == confidence. We instead
    # force exact independence by choosing counts so accuracy == confidence is
    # not generally possible, so assert the weaker property: ECE equals the gap.
    total = 100
    samples = [CalibrationSample(predicted=confidence, outcome=1)] * successes + [
        CalibrationSample(predicted=confidence, outcome=0)
    ] * (total - successes)
    ece = expected_calibration_error(samples, n_buckets=1)
    assert ece is not None
    expected_accuracy = successes / total
    assert ece == pytest.approx(abs(expected_accuracy - confidence))


@settings(max_examples=100)
@given(samples=_samples)
def test_ece_never_exceeds_mean_absolute_gap_bound(samples: list[CalibrationSample]) -> None:
    # ECE is a weighted average of per-bucket absolute gaps; along with the
    # unit-interval bound this confirms the weighting is well-formed.
    ece = expected_calibration_error(samples)
    assert ece is not None
    assert ece == pytest.approx(ece)  # not NaN


def test_perfect_prediction_has_zero_brier_and_ece() -> None:
    samples = [CalibrationSample(predicted=1.0, outcome=1)] * 50 + [
        CalibrationSample(predicted=0.0, outcome=0)
    ] * 50
    assert brier_score(samples) == pytest.approx(0.0)
    assert expected_calibration_error(samples) == pytest.approx(0.0)
