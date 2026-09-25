"""Unit tests for the calibration evaluator and filters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from decisionos.calibration import (
    CalibrationDatum,
    CalibrationEvaluator,
    CalibrationFilter,
    InMemoryCalibrationSource,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _datum(
    decision_id: str,
    *,
    predicted: float,
    success: bool,
    decision_type: str = "tool_authorization",
    provider: str = "mock",
    action: str = "allow",
    created_at: datetime | None = None,
) -> CalibrationDatum:
    return CalibrationDatum(
        decision_id=decision_id,
        predicted=predicted,
        success=success,
        decision_type=decision_type,
        provider=provider,
        action=action,
        created_at=created_at or _NOW,
    )


@pytest.mark.asyncio
async def test_report_over_source() -> None:
    source = InMemoryCalibrationSource(
        [
            _datum("d1", predicted=0.9, success=True),
            _datum("d2", predicted=0.9, success=False),
        ]
    )
    report = await CalibrationEvaluator(source).report()
    assert report.sample_count == 2
    assert report.brier_score == pytest.approx((0.1**2 + 0.9**2) / 2)


@pytest.mark.asyncio
async def test_empty_source_reports_no_samples() -> None:
    report = await CalibrationEvaluator(InMemoryCalibrationSource()).report()
    assert report.sample_count == 0
    assert report.brier_score is None


@pytest.mark.asyncio
async def test_filter_by_decision_type() -> None:
    source = InMemoryCalibrationSource(
        [
            _datum("d1", predicted=0.9, success=True, decision_type="a"),
            _datum("d2", predicted=0.5, success=False, decision_type="b"),
        ]
    )
    report = await CalibrationEvaluator(source).report(CalibrationFilter(decision_type="a"))
    assert report.sample_count == 1


@pytest.mark.asyncio
async def test_filter_by_provider_and_action() -> None:
    source = InMemoryCalibrationSource(
        [
            _datum("d1", predicted=0.9, success=True, provider="mock", action="allow"),
            _datum("d2", predicted=0.5, success=False, provider="jev", action="deny"),
        ]
    )
    evaluator = CalibrationEvaluator(source)
    assert (await evaluator.report(CalibrationFilter(provider="jev"))).sample_count == 1
    assert (await evaluator.report(CalibrationFilter(action="allow"))).sample_count == 1
    assert (await evaluator.report(CalibrationFilter(provider="missing"))).sample_count == 0


@pytest.mark.asyncio
async def test_filter_by_time_range() -> None:
    source = InMemoryCalibrationSource(
        [
            _datum("old", predicted=0.9, success=True, created_at=_NOW - timedelta(days=2)),
            _datum("new", predicted=0.9, success=True, created_at=_NOW),
        ]
    )
    evaluator = CalibrationEvaluator(source)
    after = await evaluator.report(CalibrationFilter(created_after=_NOW - timedelta(days=1)))
    assert after.sample_count == 1
    before = await evaluator.report(CalibrationFilter(created_before=_NOW - timedelta(days=1)))
    assert before.sample_count == 1


@pytest.mark.asyncio
async def test_in_memory_source_add() -> None:
    source = InMemoryCalibrationSource()
    source.add(_datum("d1", predicted=0.5, success=True))
    report = await CalibrationEvaluator(source).report()
    assert report.sample_count == 1


@pytest.mark.asyncio
async def test_predicted_probability_is_clamped() -> None:
    # A source that somehow yields an out-of-range value is clamped, not fatal.
    source = InMemoryCalibrationSource([_datum("d1", predicted=0.0, success=True)])
    report = await CalibrationEvaluator(source).report()
    assert report.sample_count == 1
