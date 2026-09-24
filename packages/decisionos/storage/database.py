"""Database engine, session factory, and declarative base.

SQLAlchemy 2.0 async. The engine is created lazily from :class:`Settings` and
reused for the process lifetime. Sessions are produced by an
``async_sessionmaker`` and used through explicit ``async with`` blocks or the
``session_scope`` helper.

Nothing in this module opens a connection at import time, so importing the
storage package is safe in environments without a database (for example during
unit tests that only exercise pure logic).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from decisionos.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base for all DecisionOS ORM models."""


class Database:
    """Owns the async engine and session factory.

    Parameters
    ----------
    settings:
        Resolved settings. Defaults to the process settings.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(
                self._settings.database_url,
                pool_size=self._settings.database_pool_size,
                max_overflow=self._settings.database_max_overflow,
                echo=self._settings.database_echo,
                pool_pre_ping=True,
            )
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker is None:
            self._sessionmaker = async_sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._sessionmaker

    def session(self) -> AsyncSession:
        """Create a new session. Caller owns its lifecycle."""
        return self.sessionmaker()

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        """Yield a session inside a transaction, committing on success."""
        session = self.session()
        try:
            async with session.begin():
                yield session
        finally:
            await session.close()

    async def dispose(self) -> None:
        """Dispose of the engine and its connection pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None

    async def create_all(self) -> None:
        """Create all tables. Intended for tests and local bootstrap only."""
        # Import models so they are registered on Base.metadata.
        import decisionos.storage.models  # noqa: F401

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Drop all tables. Intended for tests and local bootstrap only."""
        import decisionos.storage.models  # noqa: F401

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


_DATABASE: Database | None = None


def get_database(settings: Settings | None = None) -> Database:
    """Return the process-wide :class:`Database`."""
    global _DATABASE
    if _DATABASE is None or settings is not None:
        _DATABASE = Database(settings)
    return _DATABASE


async def dispose_database() -> None:
    """Dispose of the process-wide database, if any."""
    global _DATABASE
    if _DATABASE is not None:
        await _DATABASE.dispose()
        _DATABASE = None


__all__ = [
    "Base",
    "Database",
    "dispose_database",
    "get_database",
]
