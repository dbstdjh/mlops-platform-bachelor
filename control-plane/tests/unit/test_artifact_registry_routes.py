import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.entities.artifact_registry import ArtifactRegistryStatus, RegistryTokenIssuedResponse
from src.core.entities.deployment import DeploymentResponse
from src.presentation.api.v1 import artifact_registry
from src.presentation.dependencies import get_artifact_registry_service, get_current_user, get_current_user_id


def create_test_app(service):
    app = FastAPI()
    app.include_router(artifact_registry.router, prefix="/api/v1")
    app.dependency_overrides[get_artifact_registry_service] = lambda: service
    app.dependency_overrides[get_current_user_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="user@example.com",
    )
    return app


@pytest.mark.asyncio
async def test_enable_artifact_registry_returns_status():
    service = SimpleNamespace(
        enable=AsyncMock(
            return_value=ArtifactRegistryStatus(
                enabled=True,
                registry_host="gitea.mldlc.local",
                username="mldlc-user",
                namespace="gitea.mldlc.local/mldlc-user",
                docker_login_command="docker login gitea.mldlc.local -u mldlc-user --password-stdin",
            )
        )
    )
    app = create_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/artifact-registry:enable")

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    service.enable.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_registry_token_returns_plaintext_once():
    service = SimpleNamespace(
        create_token=AsyncMock(
            return_value=RegistryTokenIssuedResponse(
                name="workstation",
                token_last_eight="aintext",
                token="workstation-plaintext",
                registry_host="gitea.mldlc.local",
                username="mldlc-user",
                docker_login_command="docker login gitea.mldlc.local -u mldlc-user --password-stdin",
            )
        )
    )
    app = create_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/artifact-registry/tokens", json={"name": "workstation"})

    assert response.status_code == 201
    assert response.json()["token"] == "workstation-plaintext"


@pytest.mark.asyncio
async def test_create_image_deployment_uses_nested_image_tag_route():
    service = SimpleNamespace(
        create_image_deployment=AsyncMock(
            return_value=DeploymentResponse(
                name="fraud-prod",
                slug="fraud-prod",
                status="PENDING",
                created_at="2026-01-01T00:00:00Z",
                source_type="image",
                image_ref="gitea.mldlc.local/mldlc-user/fraud:latest",
            )
        )
    )
    app = create_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/artifact-registry/images/fraud/tags/latest/deployments",
            json={"name": "fraud-prod"},
        )

    assert response.status_code == 201
    assert response.json()["source_type"] == "image"
    service.create_image_deployment.assert_awaited_once()
    assert service.create_image_deployment.await_args.args[1:3] == ("fraud", "latest")
