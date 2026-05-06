from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_dep() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency version of get_db."""
    async with get_db() as session:
        yield session


async def init_db() -> None:
    """Create all tables on startup (dev only — use Alembic in production)."""
    from . import models  # noqa: F401 — ensure all models are imported

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
