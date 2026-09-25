"""Unit tests for calibration metrics."""

from __future__ import annotations

import pytest

from decisionos.calibration import (
    CalibrationSample,
    brier_score,
    compute_report,
    expected_calibration_error,
    reliability_buckets,
)


def test_sample_validates_predicted_range() -> None:
    with pytest.raises(ValueError, match="out of range"):
        CalibrationSample(predicted=1.5, outcome=1)
    with pytest.raises(ValueError, match="out of range"):
        CalibrationSample(predicted=-0.1, outcome=0)


def test_sample_validates_outcome() -> None:
    with pytest.raises(ValueError, match="outcome"):
        CalibrationSample(predicted=0.5, outcome=2)


def test_empty_inputs_return_none() -> None:
    assert brier_score([]) is None
    assert expected_calibration_error([]) is None
    assert reliability_buckets([]) == []


def test_brier_score_perfect_prediction_is_zero() -> None:
    samples = [
        CalibrationSample(predicted=1.0, outcome=1),
        CalibrationSample(predicted=0.0, outcome=0),
    ]
    assert brier_score(samples) == pytest.approx(0.0)


def test_brier_score_known_value() -> None:
    samples = [
        CalibrationSample(predicted=0.95, outcome=1),
        CalibrationSample(predicted=0.95, outcome=1),
        CalibrationSample(predicted=0.55, outcome=0),
        CalibrationSample(predicted=0.65, outcome=1),
    ]
    # (0.05^2 + 0.05^2 + 0.55^2 + 0.35^2) / 4 = 0.43 / 4
    assert brier_score(samples) == pytest.approx(0.1075)


def test_brier_score_penalises_confident_errors() -> None:
    confident_wrong = [CalibrationSample(predicted=0.99, outcome=0)]
    timid_wrong = [CalibrationSample(predicted=0.51, outcome=0)]
    assert brier_score(confident_wrong) > brier_score(timid_wrong)


def test_reliability_buckets_group_by_probability() -> None:
    samples = [
        CalibrationSample(predicted=0.55, outcome=0),
        CalibrationSample(predicted=0.65, outcome=1),
        CalibrationSample(predicted=0.95, outcome=1),
        CalibrationSample(predicted=0.95, outcome=1),
    ]
    buckets = {round(b.lower, 1): b for b in reliability_buckets(samples, n_buckets=5)}
    assert set(buckets) == {0.4, 0.6, 0.8}
    assert buckets[0.4].count == 1
    assert buckets[0.4].accuracy == pytest.approx(0.0)
    assert buckets[0.4].avg_confidence == pytest.approx(0.55)
    assert buckets[0.8].count == 2
    assert buckets[0.8].accuracy == pytest.approx(1.0)


def test_prediction_of_one_falls_into_last_bucket() -> None:
    buckets = reliability_buckets([CalibrationSample(predicted=1.0, outcome=1)], n_buckets=10)
    assert len(buckets) == 1
    assert buckets[0].lower == pytest.approx(0.9)
    assert buckets[0].upper == pytest.approx(1.0)


def test_empty_buckets_are_omitted() -> None:
    buckets = reliability_buckets([CalibrationSample(predicted=0.05, outcome=1)], n_buckets=10)
    assert len(buckets) == 1


def test_ece_perfect_calibration_is_zero() -> None:
    # Within each bucket, mean confidence equals observed accuracy.
    samples = [CalibrationSample(predicted=0.15, outcome=0)] * 85 + [
        CalibrationSample(predicted=0.15, outcome=1)
    ] * 15
    # expected accuracy 15%, mean confidence 15%.
    assert expected_calibration_error(samples, n_buckets=10) == pytest.approx(0.0)


def test_ece_known_value() -> None:
    samples = [
        CalibrationSample(predicted=0.95, outcome=1),
        CalibrationSample(predicted=0.95, outcome=1),
        CalibrationSample(predicted=0.55, outcome=0),
        CalibrationSample(predicted=0.65, outcome=1),
    ]
    assert expected_calibration_error(samples, n_buckets=5) == pytest.approx(0.25)


def test_ece_between_zero_and_one() -> None:
    samples = [
        CalibrationSample(predicted=p, outcome=o)
        for p, o in [(0.1, 0), (0.3, 1), (0.5, 1), (0.9, 0), (1.0, 1)]
    ]
    ece = expected_calibration_error(samples, n_buckets=5)
    assert ece is not None
    assert 0.0 <= ece <= 1.0


def test_n_buckets_must_be_positive() -> None:
    with pytest.raises(ValueError):
        reliability_buckets([CalibrationSample(predicted=0.5, outcome=1)], n_buckets=0)


def test_compute_report_empty() -> None:
    report = compute_report([])
    assert report.sample_count == 0
    assert report.brier_score is None
    assert report.expected_calibration_error is None
    assert report.buckets == []


def test_compute_report_populated() -> None:
    samples = [
        CalibrationSample(predicted=0.95, outcome=1),
        CalibrationSample(predicted=0.55, outcome=0),
    ]
    report = compute_report(samples, n_buckets=5)
    assert report.sample_count == 2
    assert report.brier_score is not None
    assert report.expected_calibration_error is not None
    assert len(report.buckets) == 2
