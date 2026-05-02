from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.config import get_settings
from src.infrastructure.database import models  # noqa: F401 — register all ORM models
from src.infrastructure.database.session import Base, configure_database
from src.presentation.api.v1 import (
    artifact_registry,
    datasets,
    deployments,
    experiments,
    health,
    models as models_router,
    overview,
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
            await conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION notify_deployment_task()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        PERFORM pg_notify('deployment_tasks', '');
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
            )
            await conn.execute(text("DROP TRIGGER IF EXISTS deployment_task_inserted ON deployment_task"))
            await conn.execute(
                text(
                    """
                    CREATE TRIGGER deployment_task_inserted
                        AFTER INSERT ON deployment_task
                        FOR EACH ROW
                        EXECUTE FUNCTION notify_deployment_task();
                    """
                )
            )

        yield
        await engine.dispose()

    app = FastAPI(
        title="MLOps Control Plane",
        description="Control Plane API for the MLOps platform",
        version="0.1.0",
        lifespan=lifespan,
    )
    configure_database(app, **database_overrides)
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(users.router, prefix="/api/v1", tags=["users"])
    app.include_router(overview.router, prefix="/api/v1", tags=["overview"])
    app.include_router(artifact_registry.router, prefix="/api/v1", tags=["artifact-registry"])
    app.include_router(datasets.router, prefix="/api/v1", tags=["datasets"])
    app.include_router(experiments.router, prefix="/api/v1", tags=["experiment-tracking"])
    app.include_router(models_router.router, prefix="/api/v1", tags=["model-registry"])
    app.include_router(deployments.router, prefix="/api/v1", tags=["deployments"])
    return app


app = create_app()
