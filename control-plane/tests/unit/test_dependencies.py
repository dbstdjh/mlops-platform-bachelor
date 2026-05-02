import uuid
from types import SimpleNamespace

import pytest

from src.application.api_key_service import ApiKeyService
from src.application.artifact_registry_service import ArtifactRegistryService
from src.application.dataset_service import DatasetService
from src.application.experiment_tracking_service import ExperimentTrackingService
from src.application.model_registry_service import ModelRegistryService
from src.config import Settings
from src.infrastructure.storage.minio_adapter import MinioStorageAdapter
from src.presentation import dependencies


def test_get_minio_client_builds_client_from_settings(monkeypatch):
    captured: dict[str, object] = {}

    class FakeMinio:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(dependencies, "Minio", FakeMinio)
    settings = Settings(
        minio_endpoint="minio.internal:9000",
        minio_access_key="access",
        minio_secret_key="secret",
        minio_use_ssl=True,
    )

    client = dependencies.get_minio_client(settings)

    assert isinstance(client, FakeMinio)
    assert captured == {
        "endpoint": "minio.internal:9000",
        "access_key": "access",
        "secret_key": "secret",
        "secure": True,
        "region": "us-east-1",
    }


def test_get_storage_wraps_injected_client():
    client = object()
    settings = Settings()

    storage = dependencies.get_storage(client, settings)

    assert isinstance(storage, MinioStorageAdapter)
    assert storage._client is client
    assert storage._presign_client is client


def test_get_storage_builds_distinct_presign_client_when_public_endpoint_configured(monkeypatch):
    client = object()
    captured: dict[str, object] = {}

    class FakeMinio:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(dependencies, "Minio", FakeMinio)
    settings = Settings(
        minio_public_endpoint="localhost:9000",
        minio_public_use_ssl=False,
        minio_access_key="access",
        minio_secret_key="secret",
    )

    storage = dependencies.get_storage(client, settings)

    assert isinstance(storage, MinioStorageAdapter)
    assert storage._client is client
    assert isinstance(storage._presign_client, FakeMinio)
    assert captured == {
        "endpoint": "localhost:9000",
        "access_key": "access",
        "secret_key": "secret",
        "secure": False,
        "region": "us-east-1",
    }


@pytest.mark.asyncio
async def test_get_dataset_service_wires_expected_dependencies():
    session = object()
    storage = object()

    service = await dependencies.get_dataset_service(session=session, storage=storage)

    assert isinstance(service, DatasetService)
    assert service._storage is storage
    assert service._dataset_repo._session is session
    assert service._resource_repo._session is session


@pytest.mark.asyncio
async def test_get_model_registry_service_wires_expected_dependencies():
    session = object()
    storage = object()

    service = await dependencies.get_model_registry_service(session=session, storage=storage)

    assert isinstance(service, ModelRegistryService)
    assert service._storage is storage
    assert service._model_repo_repo._session is session
    assert service._model_repo._session is session
    assert service._resource_repo._session is session
    assert service._experiment_repo._session is session
    assert service._run_repo._session is session


@pytest.mark.asyncio
async def test_get_experiment_tracking_service_wires_expected_dependencies():
    session = object()

    service = await dependencies.get_experiment_tracking_service(session=session)

    assert isinstance(service, ExperimentTrackingService)
    assert service._experiment_repo._session is session
    assert service._run_repo._session is session
    assert service._run_step_repo._session is session
    assert service._resource_repo._session is session
    assert service._dataset_repo._session is session
    assert service._model_repo._session is session
    assert service._model_repository_repo._session is session


@pytest.mark.asyncio
async def test_get_api_key_service_wires_expected_dependencies():
    session = object()

    service = await dependencies.get_api_key_service(session=session)

    assert isinstance(service, ApiKeyService)
    assert service._api_key_repo._session is session


@pytest.mark.asyncio
async def test_get_artifact_registry_service_wires_expected_dependencies():
    session = object()
    gitea_client = object()
    settings = Settings(gitea_public_url="http://gitea.mldlc.local")

    service = await dependencies.get_artifact_registry_service(
        session=session,
        settings=settings,
        gitea_client=gitea_client,
    )

    assert isinstance(service, ArtifactRegistryService)
    assert service._gitea_client is gitea_client
    assert service._feature_repo._session is session
    assert service._deployment_repo._session is session


@pytest.mark.asyncio
async def test_get_current_user_id_returns_authenticated_user_id():
    user_id = uuid.uuid4()

    result = await dependencies.get_current_user_id(SimpleNamespace(id=user_id))

    assert result == user_id
