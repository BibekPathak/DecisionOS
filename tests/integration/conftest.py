"""Fixtures for integration tests that require PostgreSQL and Redis.

Integration tests are skipped automatically when no database is reachable, so
the unit suite still runs on a machine without services. Set
``DECISIONOS_TEST_DATABASE_URL`` to point at a disposable database.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from decisionos.storage.database import Base

TEST_DATABASE_URL = os.environ.get(
    "DECISIONOS_TEST_DATABASE_URL",
    "postgresql+asyncpg://decisionos:decisionos@localhost:5432/decisionos_test",
)
ADMIN_DATABASE_URL = os.environ.get(
    "DECISIONOS_ADMIN_DATABASE_URL",
    "postgresql+asyncpg://decisionos:decisionos@localhost:5432/decisionos",
)


async def _ensure_test_database() -> bool:
    """Create the test database if it does not exist. Returns availability."""
    try:
        admin = create_async_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
        async with admin.connect() as connection:
            exists = await connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'decisionos_test'")
            )
            if exists.scalar() is None:
                await connection.execute(text("CREATE DATABASE decisionos_test"))
        await admin.dispose()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def _database_available() -> bool:
    import decisionos.storage.models  # noqa: F401  (register tables)

    available = await _ensure_test_database()
    if not available:
        pytest.skip("PostgreSQL is not reachable; skipping integration test")
    return True


@pytest_asyncio.fixture()
async def engine(_database_available: bool):
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=None)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture()
async def api_client(engine):
    """An HTTP client bound to the DecisionOS app, sharing the test database.

    Runs entirely on the pytest-asyncio event loop via ASGITransport so the
    app and the test share one loop and connection pool.
    """
    import httpx

    from api.main import create_app
    from decisionos.config import Settings
    from decisionos.providers import reset_registry
    from decisionos.storage import Database
    from decisionos.storage.redis import InMemoryBackend

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=TEST_DATABASE_URL,
        rate_limit_per_minute=10_000,
    )
    database = Database(settings)
    app = create_app(settings, database=database)

    # Enter the lifespan manually so app.state is populated.
    async with app.router.lifespan_context(app):
        # Replace the Redis backend with an in-memory one for hermetic tests.
        from decisionos.storage import IdempotencyStore, RateLimiter

        in_memory = InMemoryBackend()
        app.state.redis_backend = in_memory
        app.state.idempotency = IdempotencyStore(
            in_memory, ttl_seconds=settings.idempotency_ttl_seconds
        )
        app.state.rate_limiter = RateLimiter(in_memory, limit=settings.rate_limit_per_minute)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

    await database.dispose()
    reset_registry()
