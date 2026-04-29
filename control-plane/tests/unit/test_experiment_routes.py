import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.entities.experiment_tracking import (
    ExperimentMetricResponse,
    ExperimentMetricSeries,
    ExperimentMetricsResponse,
    ExperimentResponse,
    PlotPoint,
    RunMetricResponse,
    RunRef,
    RunResponse,
    RunSummaryResponse,
)
from src.core.entities.dashboard import RunDashboardResponse
from src.presentation.api.v1 import experiments
from src.presentation.dependencies import get_current_user_id, get_experiment_tracking_service


def create_experiment_test_app(service):
    app = FastAPI()
    app.include_router(experiments.router, prefix="/api/v1")
    app.dependency_overrides[get_experiment_tracking_service] = lambda: service
    app.dependency_overrides[get_current_user_id] = lambda: uuid.UUID(
        "00000000-0000-0000-0000-000000000001"
    )
    return app


def build_run_response(run_number: int = 1, status: str = "RUNNING") -> RunResponse:
    return RunResponse(
        experiment_slug="training",
        run_number=run_number,
        status=status,
        created_at="2026-01-01T00:00:00Z",
        ended_at=None,
        dataset=None,
        model=None,
        latest_metrics={"loss": 0.8},
        labels={"team": "ml"},
    )


def build_experiment_response() -> ExperimentResponse:
    return ExperimentResponse(
        name="training",
        slug="training",
        logged_data_template=["loss", "accuracy"],
        created_at="2026-01-01T00:00:00Z",
        labels={"team": "ml"},
        run_count=2,
        latest_run=RunSummaryResponse(
            run_number=2,
            status="COMPLETED",
            created_at="2026-01-01T00:00:00Z",
            latest_metrics={"loss": 0.3},
            labels={},
        ),
    )


@pytest.mark.asyncio
async def test_create_experiment_returns_service_response():
    service = SimpleNamespace(create_experiment=AsyncMock(return_value=build_experiment_response()))
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/experiments",
            json={"name": "training", "logged_data_template": ["loss"], "labels": {"team": "ml"}},
        )

    assert response.status_code == 201
    assert response.json()["slug"] == "training"
    service.create_experiment.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_experiments_returns_service_response():
    service = SimpleNamespace(list_experiments=AsyncMock(return_value=[build_experiment_response()]))
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/experiments")

    assert response.status_code == 200
    assert response.json()[0]["slug"] == "training"


@pytest.mark.asyncio
async def test_get_experiment_returns_404_when_missing():
    service = SimpleNamespace(get_experiment=AsyncMock(return_value=None))
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/experiments/training")

    assert response.status_code == 404
    assert response.json()["detail"] == "Experiment not found"


@pytest.mark.asyncio
async def test_start_run_returns_service_response():
    service = SimpleNamespace(start_run=AsyncMock(return_value=build_run_response()))
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/experiments/training/runs", json={"labels": {"team": "ml"}})

    assert response.status_code == 201
    assert response.json()["run_number"] == 1
    assert service.start_run.await_args.args[1] == "training"


@pytest.mark.asyncio
async def test_append_run_steps_returns_ok_payload():
    service = SimpleNamespace(append_run_steps=AsyncMock(return_value=None))
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/experiments/training/runs/2/steps",
            json={"items": [{"step": 1, "logged_data": {"loss": 0.5}}]},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_get_run_metric_plot_returns_series_payload():
    service = SimpleNamespace(
        get_run_metric_plot=AsyncMock(
            return_value=RunMetricResponse(
                metric_name="loss",
                points=[PlotPoint(step=1, val=0.5, timestamp="2026-01-01T00:00:00Z")],
            )
        )
    )
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/experiments/training/runs/2/plots/loss")

    assert response.status_code == 200
    assert response.json()["metric_name"] == "loss"


@pytest.mark.asyncio
async def test_get_experiment_metric_plot_returns_series_payload():
    service = SimpleNamespace(
        get_experiment_metric_plot=AsyncMock(
            return_value=ExperimentMetricResponse(
                metric_name="loss",
                series=[
                    ExperimentMetricSeries(
                        run=RunRef(experiment_slug="training", run_number=1),
                        points=[PlotPoint(step=1, val=0.5, timestamp="2026-01-01T00:00:00Z")],
                    )
                ],
            )
        )
    )
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/experiments/training/plots/loss")

    assert response.status_code == 200
    assert response.json()["series"][0]["run"]["run_number"] == 1


@pytest.mark.asyncio
async def test_get_metrics_returns_service_payload():
    service = SimpleNamespace(get_metrics=AsyncMock(return_value=ExperimentMetricsResponse(metrics=["loss", "accuracy"])))
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/experiments/training/metrics")

    assert response.status_code == 200
    assert response.json() == {"metrics": ["loss", "accuracy"]}


@pytest.mark.asyncio
async def test_run_dashboard_routes_delegate_to_service():
    dashboard_id = uuid.uuid4()
    service = SimpleNamespace(
        list_run_dashboards=AsyncMock(
            return_value=[
                RunDashboardResponse(
                    id=dashboard_id,
                    title="Loss panel",
                    plot_type="line",
                    metrics=["loss"],
                    display_order=0,
                    iframe_url="http://grafana.local/d-solo/run-plot",
                    created_at="2026-01-01T00:00:00Z",
                )
            ]
        ),
        create_run_dashboard=AsyncMock(
            return_value=RunDashboardResponse(
                id=dashboard_id,
                title="Loss panel",
                plot_type="line",
                metrics=["loss"],
                display_order=0,
                iframe_url="http://grafana.local/d-solo/run-plot",
                created_at="2026-01-01T00:00:00Z",
            )
        ),
        update_run_dashboard=AsyncMock(
            return_value=RunDashboardResponse(
                id=dashboard_id,
                title="Loss stat",
                plot_type="stat",
                metrics=["loss"],
                display_order=0,
                iframe_url="http://grafana.local/d-solo/run-plot",
                created_at="2026-01-01T00:00:00Z",
            )
        ),
        delete_run_dashboard=AsyncMock(return_value=None),
    )
    app = create_experiment_test_app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        list_response = await client.get("/api/v1/experiments/training/runs/2/dashboards")
        create_response = await client.post(
            "/api/v1/experiments/training/runs/2/dashboards",
            json={"title": "Loss panel", "plot_type": "line", "metrics": ["loss"]},
        )
        update_response = await client.patch(
            f"/api/v1/experiments/training/runs/2/dashboards/{dashboard_id}",
            json={"title": "Loss stat", "plot_type": "stat", "metrics": ["loss"]},
        )
        delete_response = await client.delete(f"/api/v1/experiments/training/runs/2/dashboards/{dashboard_id}")

    assert list_response.status_code == 200
    assert list_response.json()[0]["title"] == "Loss panel"
    assert create_response.status_code == 201
    assert create_response.json()["plot_type"] == "line"
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Loss stat"
    assert delete_response.status_code == 204
