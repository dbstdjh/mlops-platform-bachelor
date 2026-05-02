"""
Presentation layer: Dependency injection.

Resolves concrete infrastructure implementations and wires them into application services.
This is the ONLY place where infrastructure touches application — FastAPI's DI mechanism.
"""

import uuid

from fastapi import Depends
import httpx
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dataset_service import DatasetService
from src.application.artifact_registry_service import ArtifactRegistryService, SecretCipher
from src.application.api_key_service import ApiKeyService
from src.application.deployment_service import DeploymentService
from src.application.experiment_tracking_service import ExperimentTrackingService
from src.application.model_registry_service import ModelRegistryService
from src.config import Settings, get_settings
from src.infrastructure.auth.fastapi_users import get_current_active_user
from src.infrastructure.database.session import get_db
from src.infrastructure.database.repositories import (
    SqlAlchemyApiKeyRepo,
    SqlAlchemyDashboardRepo,
    SqlAlchemyDatasetRepo,
    SqlAlchemyDeploymentRepo,
    SqlAlchemyDeploymentTaskRepo,
    SqlAlchemyExperimentRepo,
    SqlAlchemyFeatureConfigRepo,
    SqlAlchemyModelRepo,
    SqlAlchemyModelRepositoryRepo,
    SqlAlchemyResourceRepository,
    SqlAlchemyRunRepo,
    SqlAlchemyRunStepRepo,
)
from src.infrastructure.database.models import UserORM
from src.infrastructure.artifact_registry.gitea import HttpGiteaRegistryClient
from src.infrastructure.observability.grafana import HttpGrafanaDashboardClient
from src.infrastructure.storage.minio_adapter import MinioStorageAdapter


def get_minio_client(settings: Settings = Depends(get_settings)) -> Minio:
    """Provide a configured MinIO client."""
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_use_ssl,
        region=settings.minio_region,
    )


def get_storage(
    minio_client: Minio = Depends(get_minio_client),
    settings: Settings = Depends(get_settings),
) -> MinioStorageAdapter:
    """Provide the MinIO storage adapter."""
    presign_client = None
    if settings.minio_public_endpoint:
        presign_client = Minio(
            endpoint=settings.minio_public_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_public_use_ssl if settings.minio_public_use_ssl is not None else settings.minio_use_ssl,
            region=settings.minio_region,
        )
    return MinioStorageAdapter(minio_client, presign_client=presign_client)


async def get_dataset_service(
    session: AsyncSession = Depends(get_db),
    storage: MinioStorageAdapter = Depends(get_storage),
) -> DatasetService:
    """Wire up the DatasetService with its repository and storage dependencies."""
    return DatasetService(
        dataset_repo=SqlAlchemyDatasetRepo(session),
        resource_repo=SqlAlchemyResourceRepository(session),
        storage=storage,
    )


async def get_model_registry_service(
    session: AsyncSession = Depends(get_db),
    storage: MinioStorageAdapter = Depends(get_storage),
) -> ModelRegistryService:
    """Wire up the ModelRegistryService with its repository and storage dependencies."""
    return ModelRegistryService(
        model_repo_repo=SqlAlchemyModelRepositoryRepo(session),
        model_repo=SqlAlchemyModelRepo(session),
        resource_repo=SqlAlchemyResourceRepository(session),
        experiment_repo=SqlAlchemyExperimentRepo(session),
        run_repo=SqlAlchemyRunRepo(session),
        storage=storage,
    )


async def get_deployment_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DeploymentService:
    """Wire up the DeploymentService with its repository dependencies."""
    if not isinstance(settings, Settings):
        settings = get_settings()

    return DeploymentService(
        deployment_repo=SqlAlchemyDeploymentRepo(session),
        deployment_task_repo=SqlAlchemyDeploymentTaskRepo(session),
        model_repo_repo=SqlAlchemyModelRepositoryRepo(session),
        model_repo=SqlAlchemyModelRepo(session),
        resource_repo=SqlAlchemyResourceRepository(session),
        dashboard_repo=SqlAlchemyDashboardRepo(session),
        grafana_client=HttpGrafanaDashboardClient.from_settings(
            grafana_url=settings.grafana_url,
            public_url=settings.grafana_public_url,
            admin_token=settings.grafana_admin_token,
            admin_user=settings.grafana_admin_user,
            admin_password=settings.grafana_admin_password,
            database_url=settings.database_url,
            datasource_name=settings.grafana_datasource_name,
            datasource_host=settings.grafana_datasource_host,
            datasource_port=settings.grafana_datasource_port,
            datasource_database=settings.grafana_datasource_database,
            datasource_user=settings.grafana_datasource_user,
            datasource_password=settings.grafana_datasource_password,
            datasource_sslmode=settings.grafana_datasource_sslmode,
        ),
    )


async def get_experiment_tracking_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ExperimentTrackingService:
    """Wire up the ExperimentTrackingService with its repository dependencies."""
    if not isinstance(settings, Settings):
        settings = get_settings()

    return ExperimentTrackingService(
        experiment_repo=SqlAlchemyExperimentRepo(session),
        run_repo=SqlAlchemyRunRepo(session),
        run_step_repo=SqlAlchemyRunStepRepo(session),
        resource_repo=SqlAlchemyResourceRepository(session),
        dataset_repo=SqlAlchemyDatasetRepo(session),
        model_repo=SqlAlchemyModelRepo(session),
        model_repository_repo=SqlAlchemyModelRepositoryRepo(session),
        dashboard_repo=SqlAlchemyDashboardRepo(session),
        grafana_client=HttpGrafanaDashboardClient.from_settings(
            grafana_url=settings.grafana_url,
            public_url=settings.grafana_public_url,
            admin_token=settings.grafana_admin_token,
            admin_user=settings.grafana_admin_user,
            admin_password=settings.grafana_admin_password,
            database_url=settings.database_url,
            datasource_name=settings.grafana_datasource_name,
            datasource_host=settings.grafana_datasource_host,
            datasource_port=settings.grafana_datasource_port,
            datasource_database=settings.grafana_datasource_database,
            datasource_user=settings.grafana_datasource_user,
            datasource_password=settings.grafana_datasource_password,
            datasource_sslmode=settings.grafana_datasource_sslmode,
        ),
        session=session,
    )


async def get_api_key_service(
    session: AsyncSession = Depends(get_db),
) -> ApiKeyService:
    """Wire up the ApiKeyService with its repository dependency."""
    return ApiKeyService(
        api_key_repo=SqlAlchemyApiKeyRepo(session),
    )


async def get_gitea_http_client():
    """Provide a short-lived HTTP client for Gitea API calls."""
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        yield client


def get_gitea_registry_client(
    settings: Settings = Depends(get_settings),
    http_client: httpx.AsyncClient = Depends(get_gitea_http_client),
) -> HttpGiteaRegistryClient:
    """Provide the Gitea registry adapter."""
    return HttpGiteaRegistryClient(
        base_url=settings.gitea_url,
        admin_token=settings.gitea_admin_token,
        http_client=http_client,
    )


async def get_artifact_registry_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    gitea_client: HttpGiteaRegistryClient = Depends(get_gitea_registry_client),
) -> ArtifactRegistryService:
    """Wire up the ArtifactRegistryService."""
    return ArtifactRegistryService(
        feature_repo=SqlAlchemyFeatureConfigRepo(session),
        deployment_repo=SqlAlchemyDeploymentRepo(session),
        deployment_task_repo=SqlAlchemyDeploymentTaskRepo(session),
        resource_repo=SqlAlchemyResourceRepository(session),
        gitea_client=gitea_client,
        cipher=SecretCipher(settings.secret_key),
        registry_public_url=settings.gitea_public_url,
    )


async def get_current_user(
    user: UserORM = Depends(get_current_active_user),
) -> UserORM:
    """Resolve the currently authenticated active user."""
    return user


async def get_current_user_id(
    user: UserORM = Depends(get_current_user),
) -> uuid.UUID:
    """Expose the authenticated user's internal identifier to application services."""
    return user.id
