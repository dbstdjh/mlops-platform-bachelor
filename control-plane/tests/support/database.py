import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.main import create_app


def build_test_database_urls() -> tuple[URL, URL]:
    """Return the application DB URL and an admin URL for provisioning it."""
    settings = get_settings()
    if settings.test_database_url:
        test_url = make_url(settings.test_database_url)
    else:
        base_url = make_url(settings.database_url)
        test_name = f"{base_url.database or 'mlops'}_test_{uuid.uuid4().hex}"
        test_url = base_url.set(database=test_name)

    admin_url = test_url.set(database="postgres")
    return test_url, admin_url


async def create_database(admin_engine: AsyncEngine, database_name: str) -> None:
    """Create the isolated database if it does not already exist."""
    async with admin_engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": database_name},
        )
        if exists.scalar_one_or_none() is None:
            await conn.execute(text(f'CREATE DATABASE "{database_name}"'))


async def drop_database(admin_engine: AsyncEngine, database_name: str) -> None:
    """Drop the isolated database after terminating remaining connections."""
    async with admin_engine.connect() as conn:
        await conn.execute(
            text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :database_name
                  AND pid <> pg_backend_pid()
                """
            ),
            {"database_name": database_name},
        )
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))


@asynccontextmanager
async def isolated_test_app() -> AsyncIterator[tuple[object, async_sessionmaker[AsyncSession]]]:
    """Provision a throwaway PostgreSQL database and return a test-scoped app."""
    test_url, admin_url = build_test_database_urls()
    admin_engine = create_async_engine(admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT")
    await create_database(admin_engine, test_url.database)

    test_engine = create_async_engine(test_url.render_as_string(hide_password=False), echo=False)
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    app = create_app(engine=test_engine, session_factory=session_factory)

    try:
        async with app.router.lifespan_context(app):
            yield app, session_factory
    finally:
        await test_engine.dispose()
        await drop_database(admin_engine, test_url.database)
        await admin_engine.dispose()
