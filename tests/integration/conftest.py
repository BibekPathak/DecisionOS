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
