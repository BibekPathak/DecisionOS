"""Policy endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.dependencies import PolicyServiceDep, RateLimitDep
from api.schemas import CreatePolicyRequest, PolicyResponse
from api.services import DecisionNotFoundError, InvalidPolicyError

router = APIRouter(prefix="/v1/policies", tags=["policies"])


@router.post(
    "",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a policy version",
)
async def create_policy(
    body: CreatePolicyRequest,
    service: PolicyServiceDep,
    _rate_limit: RateLimitDep,
) -> PolicyResponse:
    """Register an immutable policy version.

    ``rules`` uses the same structure as the YAML policy format: each rule has
    a ``name``, a ``when`` condition map, and an ``action`` with ``require``.
    """
    try:
        return await service.create(body)
    except InvalidPolicyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.get("", response_model=list[PolicyResponse], summary="List policies")
async def list_policies(
    service: PolicyServiceDep,
    _rate_limit: RateLimitDep,
) -> list[PolicyResponse]:
    return await service.list()


@router.get("/{key}", response_model=PolicyResponse, summary="Get a policy")
async def get_policy(
    key: str,
    service: PolicyServiceDep,
    _rate_limit: RateLimitDep,
) -> PolicyResponse:
    """Fetch a policy by ``name`` (latest version) or ``name@version``."""
    try:
        return await service.get(key)
    except DecisionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
