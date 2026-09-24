# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/packages:/app/apps

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# --- dependencies -----------------------------------------------------------
FROM base AS deps

COPY pyproject.toml README.md ./

RUN pip install --upgrade pip \
    && pip install \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.32" \
        "pydantic>=2.9" \
        "pydantic-settings>=2.6" \
        "sqlalchemy[asyncio]>=2.0.36" \
        "asyncpg>=0.30" \
        "alembic>=1.14" \
        "redis>=5.2" \
        "httpx>=0.28" \
        "structlog>=24.4" \
        "pyyaml>=6.0" \
        "typer>=0.15" \
        "rich>=13.9" \
        "opentelemetry-api>=1.29" \
        "opentelemetry-sdk>=1.29" \
        "opentelemetry-exporter-otlp-proto-http>=1.29" \
        "opentelemetry-instrumentation-fastapi>=0.50b0" \
        "prometheus-client>=0.21"

# --- runtime ----------------------------------------------------------------
FROM deps AS runtime

COPY packages ./packages
COPY apps ./apps
COPY migrations ./migrations
COPY examples ./examples
COPY pyproject.toml .env.example Makefile ./

RUN pip install --no-deps -e . || true

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
