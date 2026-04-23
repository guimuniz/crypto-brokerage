from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────
# A single engine is created at module import time and reused across requests.
# The engine manages the connection pool internally.
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    # echo=settings.debug,  # uncomment to log all SQL in development
    future=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
# expire_on_commit=False prevents lazy-loading attributes after commit, which
# would raise MissingGreenlet errors in async contexts.
AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a transactional database session per request.

    The session is committed if the request handler returns successfully,
    or rolled back on any exception — ensuring atomicity at the request level.
    Fine-grained transaction control (e.g. savepoints, nested transactions) is
    handled inside individual service methods.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Lifecycle helpers ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan_db():
    """
    Context manager used in FastAPI lifespan to warm up / shut down the pool.
    Eagerly acquires one connection to validate the database URL at startup.
    """
    async with engine.begin() as conn:
        # Lightweight connectivity check — does not create tables.
        await conn.run_sync(lambda _: None)
    yield
    await engine.dispose()
