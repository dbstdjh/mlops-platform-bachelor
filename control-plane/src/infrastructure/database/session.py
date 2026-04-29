from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""
    pass


def create_engine(database_url: str | None = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine."""
    settings = get_settings()
    return create_async_engine(database_url or settings.database_url, echo=False)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def configure_database(
    app,
    *,
    engine: AsyncEngine | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Attach database infrastructure to the FastAPI app state."""
    db_engine = engine or create_engine()
    app.state.db_engine = db_engine
    app.state.db_session_factory = session_factory or create_session_factory(db_engine)


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Resolve the session factory from FastAPI app state."""
    return request.app.state.db_session_factory


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Dependency that provides a database session per request."""
    session_factory = get_session_factory(request)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
