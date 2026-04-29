import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.entities.dataset import DatasetResponse, DatasetUploadResponse
from src.presentation.api.v1 import datasets
from src.presentation.dependencies import get_current_user_id, get_dataset_service


def create_dataset_test_app(service):
    app = FastAPI()
    app.include_router(datasets.router, prefix="/api/v1")
    app.dependency_overrides[get_dataset_service] = lambda: service
    app.dependency_overrides[get_current_user_id] = lambda: uuid.UUID(
        "00000000-0000-0000-0000-000000000001"
    )
    return app


@pytest.mark.asyncio
async def test_initiate_dataset_upload_returns_service_response():
    response_model = DatasetUploadResponse(
        dataset_slug="events",
        upload_url="https://upload.test/datasets/object",
        version=2,
    )
    service = SimpleNamespace(initiate_upload=AsyncMock(return_value=response_model))
    app = create_dataset_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/datasets:upload",
            json={"name": "events", "file_type": "csv", "labels": {"source": "sdk"}},
        )

    assert response.status_code == 201
    assert response.json()["dataset_slug"] == "events"
    service.initiate_upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_dataset_upload_decodes_keys_and_skips_empty_records():
    service = SimpleNamespace(confirm_upload=AsyncMock(return_value=True))
    app = create_dataset_test_app(service)
    user_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/datasets:confirm_upload",
            json={
                "Records": [
                    {"s3": {"object": {"key": f"{user_id}/sales%20data/v1.parquet"}}},
                    {"s3": {"object": {"key": ""}}},
                ]
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    service.confirm_upload.assert_awaited_once_with(f"{user_id}/sales data/v1.parquet")


@pytest.mark.asyncio
async def test_confirm_dataset_upload_returns_error_payload_on_failure():
    service = SimpleNamespace(confirm_upload=AsyncMock(side_effect=RuntimeError("broken webhook")))
    app = create_dataset_test_app(service)
    user_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/datasets:confirm_upload",
            json={"Records": [{"s3": {"object": {"key": f"{user_id}/events/v1.parquet"}}}]},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "error", "detail": "broken webhook"}


@pytest.mark.asyncio
async def test_get_dataset_returns_404_when_service_returns_none():
    service = SimpleNamespace(get_dataset=AsyncMock(return_value=None))
    app = create_dataset_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/datasets/events/versions/3")

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found"


@pytest.mark.asyncio
async def test_get_dataset_returns_service_payload():
    service = SimpleNamespace(
        get_dataset=AsyncMock(
            return_value=DatasetResponse(
                name="events",
                slug="events",
                version=3,
                status="READY",
                file_type="parquet",
                created_at="2026-01-01T00:00:00Z",
                labels={"team": "ml"},
            )
        )
    )
    app = create_dataset_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/datasets/events/versions/3")

    assert response.status_code == 200
    assert response.json()["slug"] == "events"


@pytest.mark.asyncio
async def test_list_datasets_returns_service_payload():
    service = SimpleNamespace(
        list_datasets=AsyncMock(
            return_value=[
                DatasetResponse(
                    name="metrics",
                    slug="metrics",
                    version=1,
                    status="PENDING",
                    file_type="csv",
                    created_at="2026-01-01T00:00:00Z",
                    labels={},
                )
            ]
        )
    )
    app = create_dataset_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/datasets")

    assert response.status_code == 200
    assert response.json()[0]["slug"] == "metrics"


@pytest.mark.asyncio
async def test_get_download_url_returns_signed_url():
    service = SimpleNamespace(get_download_url=AsyncMock(return_value="https://download.test/object"))
    app = create_dataset_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/datasets/events:download")

    assert response.status_code == 200
    assert response.json() == {"download_url": "https://download.test/object"}


@pytest.mark.asyncio
async def test_get_version_download_url_returns_signed_url():
    service = SimpleNamespace(get_version_download_url=AsyncMock(return_value="https://download.test/object"))
    app = create_dataset_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/datasets/events/versions/2:download")

    assert response.status_code == 200
    assert response.json() == {"download_url": "https://download.test/object"}


@pytest.mark.asyncio
async def test_get_version_download_url_returns_404_when_missing():
    service = SimpleNamespace(get_version_download_url=AsyncMock(return_value=None))
    app = create_dataset_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/datasets/events/versions/2:download")

    assert response.status_code == 404
    assert response.json()["detail"] == "No ready dataset found for that slug and version"
