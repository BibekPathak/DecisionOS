"""Decision schema endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.dependencies import RateLimitDep, SchemaServiceDep
from api.schemas import CreateSchemaRequest, SchemaResponse
from decisionos.engine import SchemaNotFoundError

router = APIRouter(prefix="/v1/schemas", tags=["schemas"])


@router.post(
    "",
    response_model=SchemaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a decision schema version",
)
async def create_schema(
    body: CreateSchemaRequest,
    service: SchemaServiceDep,
    _rate_limit: RateLimitDep,
) -> SchemaResponse:
    """Register an immutable schema version.

    Re-registering identical content is idempotent; registering different
    content under an existing ``name@version`` is rejected.
    """
    try:
        return await service.create(body)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("", response_model=list[SchemaResponse], summary="List decision schemas")
async def list_schemas(
    service: SchemaServiceDep,
    _rate_limit: RateLimitDep,
) -> list[SchemaResponse]:
    return await service.list()


@router.get(
    "/{name}/{version}",
    response_model=SchemaResponse,
    summary="Get a decision schema version",
)
async def get_schema(
    name: str,
    version: int,
    service: SchemaServiceDep,
    _rate_limit: RateLimitDep,
) -> SchemaResponse:
    try:
        return await service.get(name, version)
    except SchemaNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
