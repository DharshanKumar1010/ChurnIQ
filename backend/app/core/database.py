import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
_engine_kwargs: dict = {
    "echo": settings.DEBUG,
    "future": True,
    "pool_pre_ping": True,       # drops stale connections before use
}

if settings.DB_USE_NULLPOOL:
    # Supabase pgBouncer transaction mode: let the proxy own all pooling.
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
        }
    )

engine = create_async_engine(settings.async_database_url, **_engine_kwargs)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # keeps ORM objects usable after commit
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session; roll back on error, always close."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Database session rolled back due to an unhandled error")
            raise


# ---------------------------------------------------------------------------
# Startup / shutdown helpers (call from lifespan)
# ---------------------------------------------------------------------------
async def connect_db() -> None:
    """Verify the database is reachable on application startup."""
    async with engine.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("Database connection established")


async def disconnect_db() -> None:
    """Dispose the connection pool on application shutdown."""
    await engine.dispose()
    logger.info("Database connection pool disposed")
