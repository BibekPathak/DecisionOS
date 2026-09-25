"""Calibration evaluation.

Turns stored decisions and their observed outcomes into a
:class:`~decisionos.calibration.metrics.CalibrationReport`. The evaluator
depends on a :class:`CalibrationDataSource` so the computation is independent
of PostgreSQL and testable with an in-memory source.

Only decisions that have a recorded outcome contribute a sample: calibration
requires ground truth. A decision's predicted probability is its confidence in
the selected action; a successful outcome is ``1``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from decisionos.calibration.metrics import (
    CalibrationReport,
    CalibrationSample,
    compute_report,
)


@dataclass(frozen=True)
class CalibrationFilter:
    """Filters selecting which decisions contribute to calibration.

    All fields are optional; an empty filter selects every decided-and-observed
    decision.
    """

    decision_type: str | None = None
    schema_name: str | None = None
    schema_version: int | None = None
    provider: str | None = None
    action: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


@dataclass(frozen=True)
class CalibrationDatum:
    """A decision/outcome pair available for calibration."""

    decision_id: str
    predicted: float
    success: bool
    decision_type: str
    provider: str
    action: str
    created_at: datetime


@runtime_checkable
class CalibrationDataSource(Protocol):
    """Provides decision/outcome pairs matching a filter."""

    async def gather(self, filter: CalibrationFilter) -> list[CalibrationDatum]: ...


class CalibrationEvaluator:
    """Computes calibration reports from a data source.

    Parameters
    ----------
    source:
        Supplies decision/outcome pairs.
    n_buckets:
        Number of equal-width reliability buckets.
    """

    def __init__(self, source: CalibrationDataSource, *, n_buckets: int = 10) -> None:
        self._source = source
        self._n_buckets = n_buckets

    async def report(self, filter: CalibrationFilter | None = None) -> CalibrationReport:
        """Compute the calibration report for decisions matching ``filter``."""
        data = await self._source.gather(filter or CalibrationFilter())
        samples = [
            CalibrationSample(
                predicted=min(max(datum.predicted, 0.0), 1.0),
                outcome=1 if datum.success else 0,
            )
            for datum in data
        ]
        return compute_report(samples, n_buckets=self._n_buckets)


class InMemoryCalibrationSource:
    """A simple in-memory :class:`CalibrationDataSource` for tests and demos."""

    def __init__(self, data: list[CalibrationDatum] | None = None) -> None:
        self._data = list(data or [])

    def add(self, datum: CalibrationDatum) -> None:
        self._data.append(datum)

    async def gather(self, filter: CalibrationFilter) -> list[CalibrationDatum]:
        return [datum for datum in self._data if _matches(datum, filter)]


def _matches(datum: CalibrationDatum, filter: CalibrationFilter) -> bool:
    if filter.decision_type and datum.decision_type != filter.decision_type:
        return False
    if filter.provider and datum.provider != filter.provider:
        return False
    if filter.action and datum.action != filter.action:
        return False
    if filter.created_after is not None and datum.created_at < filter.created_after:
        return False
    # schema filters are matched by the data source; the in-memory source does
    # not carry schema fields, so only decisions whose source already applied
    # those filters are considered.
    return not (filter.created_before is not None and datum.created_at >= filter.created_before)


__all__ = [
    "CalibrationDataSource",
    "CalibrationDatum",
    "CalibrationEvaluator",
    "CalibrationFilter",
    "InMemoryCalibrationSource",
]
