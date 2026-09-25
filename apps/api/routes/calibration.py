"""Calibration endpoint.

Returns measured calibration (Brier score, expected calibration error, and
reliability buckets) over decisions that have a recorded outcome. Results can
be filtered by decision type, schema, provider, action, and time range.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from api.dependencies import CalibrationServiceDep, RateLimitDep
from api.schemas import CalibrationResponse
from decisionos.calibration import CalibrationFilter

router = APIRouter(prefix="/v1/calibration", tags=["calibration"])


@router.get("", response_model=CalibrationResponse, summary="Calibration report")
async def calibration_report(
    service: CalibrationServiceDep,
    _rate_limit: RateLimitDep,
    decision_type: Annotated[str | None, Query()] = None,
    schema_name: Annotated[str | None, Query()] = None,
    schema_version: Annotated[int | None, Query(ge=1)] = None,
    provider: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
) -> CalibrationResponse:
    """Return calibration statistics for decisions matching the filters.

    The sample set is every decision with a recorded outcome that matches the
    filters. When no decisions qualify, ``sample_count`` is ``0`` and the
    metrics are ``null`` rather than fabricated.
    """
    params = CalibrationFilter(
        decision_type=decision_type,
        schema_name=schema_name,
        schema_version=schema_version,
        provider=provider,
        action=action,
        created_after=created_after,
        created_before=created_before,
    )
    return await service.report(params)
