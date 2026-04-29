import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.entities.model import ModelResponse, ModelUploadResponse
from src.core.entities.model_repository import ModelRepositoryResponse
from src.presentation.api.v1 import models
from src.presentation.dependencies import get_current_user_id, get_model_registry_service


def create_model_test_app(service):
    app = FastAPI()
    app.include_router(models.router, prefix="/api/v1")
    app.dependency_overrides[get_model_registry_service] = lambda: service
    app.dependency_overrides[get_current_user_id] = lambda: uuid.UUID(
        "00000000-0000-0000-0000-000000000001"
    )
    return app


def build_repository_response(name: str, slug: str) -> ModelRepositoryResponse:
    return ModelRepositoryResponse(
        name=name,
        slug=slug,
        is_deleted=False,
        created_at="2026-01-01T00:00:00Z",
        labels={"scope": "test"},
    )


def build_model_response(repository_slug: str, name: str, version: str = "1.0") -> ModelResponse:
    return ModelResponse(
        repository_slug=repository_slug,
        name=name,
        version=version,
        run=None,
        is_deleted=False,
        s3_uri=None,
        status="PENDING",
        created_at="2026-01-01T00:00:00Z",
        labels={"framework": "pytorch"},
    )


@pytest.mark.asyncio
async def test_create_repository_returns_service_response():
    service = SimpleNamespace(create_repository=AsyncMock(return_value=build_repository_response("fraud", "fraud")))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/repositories", json={"name": "fraud", "labels": {"scope": "test"}})

    assert response.status_code == 201
    assert response.json()["slug"] == "fraud"
    service.create_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_repositories_returns_service_response():
    service = SimpleNamespace(list_repositories=AsyncMock(return_value=[build_repository_response("catalog", "catalog")]))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/repositories")

    assert response.status_code == 200
    assert response.json()[0]["slug"] == "catalog"


@pytest.mark.asyncio
async def test_get_repository_returns_404_when_missing():
    service = SimpleNamespace(get_repository=AsyncMock(return_value=None))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/repositories/catalog")

    assert response.status_code == 404
    assert response.json()["detail"] == "Repository not found"


@pytest.mark.asyncio
async def test_delete_repository_returns_204_on_success():
    service = SimpleNamespace(delete_repository=AsyncMock(return_value=True))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/v1/repositories/catalog")

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_repository_returns_404_when_missing():
    service = SimpleNamespace(delete_repository=AsyncMock(return_value=False))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/v1/repositories/catalog")

    assert response.status_code == 404
    assert response.json()["detail"] == "Repository not found"


@pytest.mark.asyncio
async def test_create_model_uses_repository_slug_from_path():
    service = SimpleNamespace(create_model=AsyncMock(return_value=build_model_response("catalog", "segmenter")))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/repositories/catalog/models",
            json={
                "name": "segmenter",
                "version": "1.0",
                "labels": {"framework": "pytorch"},
            },
        )

    assert response.status_code == 201
    assert response.json()["repository_slug"] == "catalog"
    assert service.create_model.await_args.args[1] == "catalog"


@pytest.mark.asyncio
async def test_create_model_maps_service_error_to_404():
    service = SimpleNamespace(create_model=AsyncMock(side_effect=ValueError("missing repository")))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/repositories/catalog/models",
            json={"name": "segmenter", "version": "1.0"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "missing repository"


@pytest.mark.asyncio
async def test_list_models_returns_service_response():
    service = SimpleNamespace(list_models=AsyncMock(return_value=[build_model_response("catalog", "embedder")]))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/repositories/catalog/models")

    assert response.status_code == 200
    assert response.json()[0]["repository_slug"] == "catalog"


@pytest.mark.asyncio
async def test_get_model_returns_service_response():
    model_response = build_model_response("catalog", "classifier", version="2.0")
    service = SimpleNamespace(get_model=AsyncMock(return_value=model_response))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/repositories/catalog/models/2.0")

    assert response.status_code == 200
    assert response.json()["version"] == "2.0"


@pytest.mark.asyncio
async def test_get_model_upload_url_returns_404_when_missing():
    service = SimpleNamespace(get_upload_url=AsyncMock(return_value=None))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/repositories/catalog/models/2.0:upload")

    assert response.status_code == 404
    assert response.json()["detail"] == "Model not found"


@pytest.mark.asyncio
async def test_get_model_upload_url_returns_service_payload():
    service = SimpleNamespace(
        get_upload_url=AsyncMock(
            return_value=ModelUploadResponse(
                repository_slug="catalog",
                version="2.0",
                upload_url="https://upload.test/models/object",
            )
        )
    )
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/repositories/catalog/models/2.0:upload")

    assert response.status_code == 200
    assert response.json()["version"] == "2.0"


@pytest.mark.asyncio
async def test_confirm_model_upload_returns_404_when_missing():
    service = SimpleNamespace(confirm_upload=AsyncMock(return_value=False))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/repositories/catalog/models/2.0:confirm_upload")

    assert response.status_code == 404
    assert response.json()["detail"] == "Model not found"


@pytest.mark.asyncio
async def test_confirm_model_upload_returns_409_when_service_rejects_confirmation():
    service = SimpleNamespace(confirm_upload=AsyncMock(side_effect=ValueError("artifact missing")))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/repositories/catalog/models/2.0:confirm_upload")

    assert response.status_code == 409
    assert response.json()["detail"] == "artifact missing"


@pytest.mark.asyncio
async def test_confirm_model_upload_returns_ok_on_success():
    service = SimpleNamespace(confirm_upload=AsyncMock(return_value=True))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/repositories/catalog/models/2.0:confirm_upload")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_confirm_model_upload_webhook_decodes_keys_and_skips_empty_records():
    service = SimpleNamespace(confirm_upload_from_object_key=AsyncMock(return_value=True))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/models:confirm_upload",
            json={
                "Records": [
                    {"s3": {"object": {"key": "00000000-0000-0000-0000-000000000001/fraud/fraud%20detector/v1.0"}}},
                    {"s3": {"object": {"key": ""}}},
                ]
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    service.confirm_upload_from_object_key.assert_awaited_once_with(
        "00000000-0000-0000-0000-000000000001/fraud/fraud detector/v1.0"
    )


@pytest.mark.asyncio
async def test_confirm_model_upload_webhook_returns_error_payload_on_failure():
    service = SimpleNamespace(confirm_upload_from_object_key=AsyncMock(side_effect=RuntimeError("broken webhook")))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/models:confirm_upload",
            json={"Records": [{"s3": {"object": {"key": "00000000-0000-0000-0000-000000000001/fraud/model/v1.0"}}}]},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "error", "detail": "broken webhook"}


@pytest.mark.asyncio
async def test_get_model_download_url_returns_404_when_missing():
    service = SimpleNamespace(get_download_url=AsyncMock(return_value=None))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/repositories/catalog/models/2.0:download")

    assert response.status_code == 404
    assert response.json()["detail"] == "No ready model found with that version"


@pytest.mark.asyncio
async def test_get_model_download_url_returns_signed_url():
    service = SimpleNamespace(get_download_url=AsyncMock(return_value="https://download.test/models/object"))
    app = create_model_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/repositories/catalog/models/2.0:download")

    assert response.status_code == 200
    assert response.json() == {"download_url": "https://download.test/models/object"}
