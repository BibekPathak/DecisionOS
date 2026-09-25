"""A PostgreSQL-backed calibration data source.

Joins decisions with their recorded outcomes and returns the predicted
probability / observed success pairs the calibration metrics consume. Kept in
the calibration package so the query lives next to the metric it feeds, while
depending only on the storage layer's ORM models.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decisionos.calibration.evaluator import (
    CalibrationDatum,
    CalibrationFilter,
)
from decisionos.storage.models import DecisionOutcomeRow, DecisionRow


class DatabaseCalibrationSource:
    """A :class:`~decisionos.calibration.evaluator.CalibrationDataSource` over the DB."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def gather(self, filter: CalibrationFilter) -> list[CalibrationDatum]:
        statement = (
            select(
                DecisionRow.id,
                DecisionRow.confidence,
                DecisionRow.decision_type,
                DecisionRow.provider,
                DecisionRow.action,
                DecisionRow.created_at,
                DecisionOutcomeRow.success,
            )
            .join(DecisionOutcomeRow, DecisionOutcomeRow.decision_id == DecisionRow.id)
            .order_by(DecisionRow.created_at)
        )

        if filter.decision_type:
            statement = statement.where(DecisionRow.decision_type == filter.decision_type)
        if filter.schema_name:
            statement = statement.where(DecisionRow.schema_name == filter.schema_name)
        if filter.schema_version is not None:
            statement = statement.where(DecisionRow.schema_version == filter.schema_version)
        if filter.provider:
            statement = statement.where(DecisionRow.provider == filter.provider)
        if filter.action:
            statement = statement.where(DecisionRow.action == filter.action)
        if filter.created_after is not None:
            statement = statement.where(DecisionRow.created_at >= filter.created_after)
        if filter.created_before is not None:
            statement = statement.where(DecisionRow.created_at < filter.created_before)

        result = await self._session.execute(statement)
        return [
            CalibrationDatum(
                decision_id=row.id,
                predicted=float(row.confidence),
                success=bool(row.success),
                decision_type=row.decision_type,
                provider=row.provider,
                action=row.action,
                created_at=row.created_at,
            )
            for row in result.all()
        ]


__all__ = ["DatabaseCalibrationSource"]
