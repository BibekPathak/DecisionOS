"""FastAPI dependencies and application wiring.

The application stores long-lived collaborators (database, provider registry,
Redis-backed stores, settings) on ``app.state`` during startup. Dependencies
here pull them back out and build request-scoped services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import (
    CalibrationService,
    DecisionService,
    PolicyService,
    SchemaService,
)
from decisionos.config import Settings
from decisionos.engine import DecisionEvaluator
from decisionos.observability.logging import get_logger
from decisionos.providers import ProviderRegistry
from decisionos.storage import (
    Database,
    DecisionRepository,
    DecisionSchemaRepository,
    IdempotencyStore,
    PolicyRepository,
    RateLimiter,
)

logger = get_logger(__name__)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_provider_registry(request: Request) -> ProviderRegistry:
    return request.app.state.provider_registry


def get_idempotency_store(request: Request) -> IdempotencyStore:
    return request.app.state.idempotency


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session inside a transaction."""
    database: Database = request.app.state.database
    session = database.session()
    try:
        async with session.begin():
            yield session
    finally:
        await session.close()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def require_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Enforce API-key authentication when configured.

    In development and test the check is disabled. The key may be supplied via
    ``X-API-Key`` or ``Authorization: Bearer <key>``. The presented value is
    never logged.
    """
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return
    expected = settings.api_key.get_secret_value().strip()
    if not expected:
        # Auth is enabled but no key is configured; fail closed.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key authentication is enabled but no key is configured",
        )
    presented = x_api_key
    if presented is None and authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:]
    if presented != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


AuthDep = Annotated[None, Depends(require_api_key)]


def get_decision_service(request: Request, session: SessionDep) -> DecisionService:
    evaluator = DecisionEvaluator(
        request.app.state.provider_registry,
        DecisionSchemaRepository(session),
    )
    return DecisionService(
        evaluator=evaluator,
        decisions=DecisionRepository(session),
        schemas=DecisionSchemaRepository(session),
        policies=PolicyRepository(session),
    )


def get_schema_service(session: SessionDep) -> SchemaService:
    return SchemaService(DecisionSchemaRepository(session))


def get_policy_service(session: SessionDep) -> PolicyService:
    return PolicyService(PolicyRepository(session))


def get_calibration_service(session: SessionDep) -> CalibrationService:
    del session  # Phase 9 will read outcomes through the repository.
    return CalibrationService()


DecisionServiceDep = Annotated[DecisionService, Depends(get_decision_service)]
SchemaServiceDep = Annotated[SchemaService, Depends(get_schema_service)]
PolicyServiceDep = Annotated[PolicyService, Depends(get_policy_service)]
CalibrationServiceDep = Annotated[CalibrationService, Depends(get_calibration_service)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


async def enforce_rate_limit(limiter: RateLimiterDep, request: Request) -> None:
    """Apply the configured rate limit per client identifier.

    The identifier is the API key when present, otherwise the client host.
    Exceeding the limit yields ``429`` with a ``Retry-After`` header.
    """
    identifier = request.headers.get("X-API-Key") or (
        request.client.host if request.client else "anonymous"
    )
    result = await limiter.check(identifier)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(result.retry_after_seconds or 60)},
        )


RateLimitDep = Annotated[None, Depends(enforce_rate_limit)]

__all__ = [
    "AuthDep",
    "CalibrationServiceDep",
    "DecisionServiceDep",
    "IdempotencyDep",
    "PolicyServiceDep",
    "RateLimitDep",
    "RateLimiterDep",
    "SchemaServiceDep",
    "SessionDep",
    "SettingsDep",
    "enforce_rate_limit",
    "get_database",
    "get_idempotency_store",
    "get_rate_limiter",
    "get_settings",
]
