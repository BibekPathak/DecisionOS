"""Calibration endpoint.

Real Brier score, expected calibration error, and reliability buckets are
implemented in Phase 9. Until then the endpoint returns an empty, honestly
labelled report rather than fabricated statistics.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.dependencies import CalibrationServiceDep, RateLimitDep
from api.schemas import CalibrationResponse

router = APIRouter(prefix="/v1/calibration", tags=["calibration"])


@router.get("", response_model=CalibrationResponse, summary="Calibration report")
async def calibration_report(
    service: CalibrationServiceDep,
    _rate_limit: RateLimitDep,
) -> CalibrationResponse:
    return await service.report()
