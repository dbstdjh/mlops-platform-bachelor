from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.infrastructure.database import models  # noqa: F401 — register all ORM models
from src.infrastructure.database.session import Base, configure_database
from src.presentation.api.v1 import (
    experiments,
    health,
    datasets,
    models as models_router,
    users,
)


def create_app(**database_overrides) -> FastAPI:
    """Application factory that supports injecting test-scoped database objects."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan — startup and shutdown hooks."""
        engine = app.state.db_engine

        # Create tables on startup (dev only — use Alembic migrations in production)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield
        await engine.dispose()

    app = FastAPI(
        title="MLOps Control Plane",
        description="Control Plane API for the MLOps platform",
        version="0.1.0",
        lifespan=lifespan,
    )
    configure_database(app, **database_overrides)

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(users.router, prefix="/api/v1", tags=["users"])
    app.include_router(datasets.router, prefix="/api/v1", tags=["datasets"])
    app.include_router(experiments.router, prefix="/api/v1", tags=["experiment-tracking"])
    app.include_router(models_router.router, prefix="/api/v1", tags=["model-registry"])
    return app


app = create_app()
