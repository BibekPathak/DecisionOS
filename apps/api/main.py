"""DecisionOS API application factory.

Phase 0 provides a minimal, bootable FastAPI app with health, readiness, and
metrics endpoints so the deployment stack can be verified. Domain routes
(decisions, schemas, policies, outcomes, calibration) are layered on in
Phases 4-6.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from decisionos import __version__
from decisionos.config import Settings, get_settings
from decisionos.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return the FastAPI application."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "test")

    app = FastAPI(
        title="DecisionOS",
        version=__version__,
        summary="A probabilistic decision runtime for AI-native software.",
        docs_url="/docs",
        redoc_url=None,
    )

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/ready", tags=["ops"], summary="Readiness probe")
    async def ready() -> dict[str, str]:
        # Dependency checks are added in later phases.
        return {"status": "ready"}

    @app.get(
        "/metrics", tags=["ops"], summary="Prometheus metrics", response_class=PlainTextResponse
    )
    async def metrics() -> str:
        from decisionos.observability.metrics import render_metrics

        return render_metrics()

    @app.on_event("startup")
    async def _on_startup() -> None:
        logger.info(
            "decisionos.api.startup",
            app_env=settings.app_env,
            default_provider=settings.default_provider,
            jev_configured=settings.jev_configured,
        )

    return app


app = create_app()
