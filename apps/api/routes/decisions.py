"""Decision endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status

from api.dependencies import (
    DecisionServiceDep,
    IdempotencyDep,
    RateLimitDep,
)
from api.schemas import (
    CreateDecisionRequest,
    DecisionResponse,
    ExplanationResponse,
    OutcomeResponse,
    RecordOutcomeRequest,
)
from api.services import DecisionNotFoundError, InvalidPolicyError
from decisionos.engine import SchemaNotFoundError
from decisionos.models import ProviderOutputError
from decisionos.providers import ProviderError
from decisionos.storage import DecisionFilter

router = APIRouter(prefix="/v1/decisions", tags=["decisions"])

# How long to wait for a concurrent request holding the same idempotency key.
_IDEMPOTENCY_WAIT_SECONDS = 5.0
_IDEMPOTENCY_POLL_SECONDS = 0.05


@router.post(
    "",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a decision",
)
async def create_decision(
    body: CreateDecisionRequest,
    service: DecisionServiceDep,
    idempotency: IdempotencyDep,
    _rate_limit: RateLimitDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> DecisionResponse:
    """Evaluate a decision request, apply policy, and persist the result.

    When an ``Idempotency-Key`` header is supplied, repeated requests with the
    same key return the original decision rather than creating a duplicate.
    """
    if idempotency_key:
        existing = await idempotency.get(idempotency_key)
        if existing is not None:
            return await _get_or_404(service, existing)

        reserved = await idempotency.reserve(idempotency_key)
        if not reserved:
            recovered = await _await_idempotent_decision(idempotency, idempotency_key)
            if recovered is not None:
                return await _get_or_404(service, recovered)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a request with this idempotency key is already in progress",
            )

        try:
            created = await service.create(body)
        except BaseException:
            await idempotency.release(idempotency_key)
            raise
        await idempotency.complete(idempotency_key, created.response.decision_id)
        return created.response

    return await _create_or_http_error(service, body)


@router.get("", response_model=list[DecisionResponse], summary="List decisions")
async def list_decisions(
    service: DecisionServiceDep,
    _rate_limit: RateLimitDep,
    decision_type: Annotated[str | None, Query()] = None,
    schema_name: Annotated[str | None, Query()] = None,
    schema_version: Annotated[int | None, Query(ge=1)] = None,
    provider: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DecisionResponse]:
    filters = DecisionFilter(
        decision_type=decision_type,
        schema_name=schema_name,
        schema_version=schema_version,
        provider=provider,
        action=action,
        state=state,
        limit=limit,
        offset=offset,
    )
    return await service.list(filters)


@router.get("/{decision_id}", response_model=DecisionResponse, summary="Get a decision")
async def get_decision(
    decision_id: str,
    service: DecisionServiceDep,
    _rate_limit: RateLimitDep,
) -> DecisionResponse:
    return await _get_or_404(service, decision_id)


@router.get(
    "/{decision_id}/explanation",
    response_model=ExplanationResponse,
    summary="Explain a decision",
)
async def explain_decision(
    decision_id: str,
    service: DecisionServiceDep,
    _rate_limit: RateLimitDep,
) -> ExplanationResponse:
    """Return structured evidence: probabilities, reason codes, and rules.

    This endpoint never fabricates prose; it reports observed facts only.
    """
    try:
        return await service.explanation(decision_id)
    except DecisionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post(
    "/{decision_id}/outcome",
    response_model=OutcomeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record the observed outcome of a decision",
)
async def record_outcome(
    decision_id: str,
    body: RecordOutcomeRequest,
    service: DecisionServiceDep,
    _rate_limit: RateLimitDep,
) -> OutcomeResponse:
    try:
        return await service.record_outcome(decision_id, body)
    except DecisionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


# --- helpers ---------------------------------------------------------------


async def _get_or_404(service: DecisionServiceDep, decision_id: str) -> DecisionResponse:
    try:
        return await service.get(decision_id)
    except DecisionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


async def _create_or_http_error(service, body: CreateDecisionRequest) -> DecisionResponse:
    try:
        created = await service.create(body)
    except SchemaNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except InvalidPolicyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    except ProviderOutputError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"provider returned an unusable decision: {error}",
        ) from error
    except ValueError as error:
        # Context size limit and other request-level validation failures.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    except ProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"provider error ({error.kind}): {error}",
        ) from error
    return created.response


async def _await_idempotent_decision(idempotency, key: str) -> str | None:
    """Wait briefly for another request to finish storing its decision id."""
    elapsed = 0.0
    while elapsed < _IDEMPOTENCY_WAIT_SECONDS:
        await asyncio.sleep(_IDEMPOTENCY_POLL_SECONDS)
        elapsed += _IDEMPOTENCY_POLL_SECONDS
        value = await idempotency.get(key)
        if value is not None:
            return value
    return None
