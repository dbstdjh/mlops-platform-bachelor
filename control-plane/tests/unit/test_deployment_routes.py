import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.entities.dashboard import DeploymentDashboardResponse, DeploymentPlotField
from src.core.entities.deployment import DeploymentResponse
from src.presentation.api.v1 import deployments
from src.presentation.dependencies import get_current_user_id, get_deployment_service


def create_deployment_test_app(service):
    app = FastAPI()
    app.include_router(deployments.router, prefix="/api/v1")
    app.dependency_overrides[get_deployment_service] = lambda: service
    app.dependency_overrides[get_current_user_id] = lambda: uuid.UUID(
        "00000000-0000-0000-0000-000000000001"
    )
    return app


def build_deployment_response(status: str = "PENDING") -> DeploymentResponse:
    return DeploymentResponse(
        name="fraud-prod",
        slug="fraud-prod",
        status=status,
        endpoint_url=None,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        created_at="2026-01-01T00:00:00Z",
        labels={"env": "test"},
    )


def build_deployment_dashboard_response() -> DeploymentDashboardResponse:
    return DeploymentDashboardResponse(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        title="Latency",
        plot_type="latency",
        source="system",
        field_path="latency_ms",
        is_system_locked=True,
        iframe_url="http://grafana.local/d-solo/latency",
        created_at="2026-01-01T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_create_model_deployment_uses_nested_model_route():
    service = SimpleNamespace(create_model_deployment=AsyncMock(return_value=build_deployment_response()))
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/repositories/fraud/models/1.0/deployments",
            json={
                "name": "fraud-prod",
                "input_schema": {"type": "object"},
                "labels": {"env": "test"},
            },
        )

    assert response.status_code == 201
    assert response.json()["slug"] == "fraud-prod"
    service.create_model_deployment.assert_awaited_once()
    assert service.create_model_deployment.await_args.args[1:3] == ("fraud", "1.0")


@pytest.mark.asyncio
async def test_create_model_deployment_maps_duplicate_to_409():
    service = SimpleNamespace(create_model_deployment=AsyncMock(side_effect=FileExistsError("duplicate")))
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/repositories/fraud/models/1.0/deployments",
            json={"name": "fraud-prod"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "duplicate"


@pytest.mark.asyncio
async def test_get_deployment_returns_404_when_missing():
    service = SimpleNamespace(get_deployment=AsyncMock(return_value=None))
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/deployments/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Deployment not found"


@pytest.mark.asyncio
async def test_list_deployment_dashboards_uses_deployment_resource_route():
    service = SimpleNamespace(
        list_deployment_dashboards=AsyncMock(return_value=[build_deployment_dashboard_response()])
    )
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/deployments/fraud-prod/dashboards")

    assert response.status_code == 200
    assert response.json()[0]["plot_type"] == "latency"
    service.list_deployment_dashboards.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_deployment_dashboard_returns_422_for_invalid_field():
    service = SimpleNamespace(
        create_deployment_dashboard=AsyncMock(side_effect=ValueError("Requested plot field is not available"))
    )
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/deployments/fraud-prod/dashboards",
            json={
                "title": "Score",
                "plot_type": "time_series",
                "source": "output",
                "field_path": "score",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Requested plot field is not available"


@pytest.mark.asyncio
async def test_create_deployment_dashboard_accepts_categorical_time_series():
    service = SimpleNamespace(
        create_deployment_dashboard=AsyncMock(
            return_value=DeploymentDashboardResponse(
                id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                title="Predictions over time",
                plot_type="category_time_series",
                source="output",
                field_path="predictions[*]",
                is_system_locked=False,
                iframe_url="http://grafana.local/d-solo/predictions",
                created_at="2026-01-01T00:00:00Z",
            )
        )
    )
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/deployments/fraud-prod/dashboards",
            json={
                "title": "Predictions over time",
                "plot_type": "category_time_series",
                "source": "output",
                "field_path": "predictions[*]",
            },
        )

    assert response.status_code == 201
    assert response.json()["plot_type"] == "category_time_series"
    service.create_deployment_dashboard.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_deployment_plot_fields_returns_plot_ready_schema_fields():
    service = SimpleNamespace(
        list_plot_fields=AsyncMock(
            return_value=[
                DeploymentPlotField(
                    source="output",
                    path="predictions[*]",
                    value_type="category_array",
                    plot_types=["distribution", "category_time_series"],
                )
            ]
        )
    )
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/deployments/fraud-prod/plot-fields")

    assert response.status_code == 200
    assert response.json() == [
        {
            "source": "output",
            "path": "predictions[*]",
            "value_type": "category_array",
            "plot_types": ["distribution", "category_time_series"],
        }
    ]


@pytest.mark.asyncio
async def test_delete_deployment_dashboard_rejects_system_panel():
    service = SimpleNamespace(
        delete_deployment_dashboard=AsyncMock(side_effect=ValueError("System deployment dashboards cannot be deleted"))
    )
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/api/v1/deployments/fraud-prod/dashboards/11111111-1111-1111-1111-111111111111"
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_deployment_returns_202_and_service_response():
    service = SimpleNamespace(delete_deployment=AsyncMock(return_value=build_deployment_response("DELETING")))
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/v1/deployments/fraud-prod")

    assert response.status_code == 202
    assert response.json()["status"] == "DELETING"


@pytest.mark.asyncio
async def test_purge_deployment_returns_204_when_deleted():
    service = SimpleNamespace(purge_deployment=AsyncMock(return_value=True))
    app = create_deployment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/v1/deployments/fraud-prod:purge")

    assert response.status_code == 204
    service.purge_deployment.assert_awaited_once()
