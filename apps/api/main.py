"""DecisionOS API application factory.

Wires the thin HTTP layer over the DecisionOS core. Long-lived collaborators
are created during startup and stored on ``app.state``; routes depend on the
service layer, which composes the engine, policy engine, and repositories.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from api.routes import calibration, decisions, policies, schemas
from decisionos import __version__
from decisionos.config import Settings, get_settings
from decisionos.observability.logging import configure_logging, get_logger
from decisionos.providers import ProviderRegistry, get_registry, reset_registry
from decisionos.storage import (
    Database,
    IdempotencyStore,
    RateLimiter,
    build_backend,
)

logger = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    provider_registry: ProviderRegistry | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Build and return the FastAPI application.

    Parameters
    ----------
    settings:
        Resolved settings. Defaults to the process settings.
    provider_registry:
        Optional pre-built registry, primarily for tests.
    database:
        Optional pre-built database, primarily for tests.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "test")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.database = database or Database(settings)
        if provider_registry is not None:
            app.state.provider_registry = provider_registry
        else:
            reset_registry()
            app.state.provider_registry = get_registry(settings)

        backend = build_backend(settings)
        app.state.redis_backend = backend
        app.state.idempotency = IdempotencyStore(
            backend, ttl_seconds=settings.idempotency_ttl_seconds
        )
        app.state.rate_limiter = RateLimiter(backend, limit=settings.rate_limit_per_minute)

        logger.info(
            "decisionos.api.startup",
            app_env=settings.app_env,
            default_provider=settings.default_provider,
            jev_configured=settings.jev_configured,
            auth_enabled=settings.auth_enabled,
        )
        try:
            yield
        finally:
            await backend.close()
            await app.state.provider_registry.aclose()
            if database is None:
                await app.state.database.dispose()
            if provider_registry is None:
                reset_registry()
            logger.info("decisionos.api.shutdown")

    app = FastAPI(
        title="DecisionOS",
        version=__version__,
        summary="A probabilistic decision runtime for AI-native software.",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    _install_error_handlers(app)
    app.include_router(decisions.router)
    app.include_router(schemas.router)
    app.include_router(policies.router)
    app.include_router(calibration.router)

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/ready", tags=["ops"], summary="Readiness probe")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get(
        "/metrics", tags=["ops"], summary="Prometheus metrics", response_class=PlainTextResponse
    )
    async def metrics() -> str:
        from decisionos.observability.metrics import render_metrics

        return render_metrics()

    return app


def _install_error_handlers(app: FastAPI) -> None:
    """Map domain exceptions to structured HTTP responses."""

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "decisionos.api.unhandled_error",
            path=request.url.path,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "an unexpected error occurred"},
        )


def build_app() -> Callable[[], FastAPI]:
    """Return a factory for ASGI servers that accept one."""
    return lambda: create_app()


app = create_app()
