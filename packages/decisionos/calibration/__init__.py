"""Calibration: measuring how well predicted probabilities match outcomes."""

from __future__ import annotations

from decisionos.calibration.evaluator import (
    CalibrationDataSource,
    CalibrationDatum,
    CalibrationEvaluator,
    CalibrationFilter,
    InMemoryCalibrationSource,
)
from decisionos.calibration.metrics import (
    CalibrationReport,
    CalibrationSample,
    ReliabilityBucket,
    brier_score,
    compute_report,
    expected_calibration_error,
    reliability_buckets,
)
from decisionos.calibration.source import DatabaseCalibrationSource

__all__ = [
    "CalibrationDataSource",
    "CalibrationDatum",
    "CalibrationEvaluator",
    "CalibrationFilter",
    "CalibrationReport",
    "CalibrationSample",
    "DatabaseCalibrationSource",
    "InMemoryCalibrationSource",
    "ReliabilityBucket",
    "brier_score",
    "compute_report",
    "expected_calibration_error",
    "reliability_buckets",
]
