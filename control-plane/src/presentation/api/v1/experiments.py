"""
Presentation layer: Experiment Tracking API routes.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.experiment_tracking_service import (
    ExperimentTrackingConflictError,
    ExperimentTrackingNotFoundError,
    ExperimentTrackingService,
    ExperimentTrackingValidationError,
)
from src.core.entities.experiment_tracking import (
    ExperimentCreate,
    ExperimentMetricResponse,
    ExperimentMetricsResponse,
    ExperimentResponse,
    RunCreate,
    RunMetricResponse,
    RunResponse,
    RunStepBatchCreate,
)
from src.core.entities.dashboard import RunDashboardCreate, RunDashboardResponse, RunDashboardUpdate
from src.core.entities.pagination import PaginatedResponse, SortDirection
from src.presentation.api.v1.pagination import LimitQuery, OffsetQuery, SearchQuery
from src.presentation.dependencies import get_current_user_id, get_experiment_tracking_service

router = APIRouter()


@router.post("/experiments", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    data: ExperimentCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Create an experiment."""
    return await service.create_experiment(user_id, data)


@router.get("/experiments", response_model=list[ExperimentResponse] | PaginatedResponse[ExperimentResponse])
async def list_experiments(
    paginated: bool = False,
    search: SearchQuery = None,
    sort_by: str = "created_at",
    sort_dir: SortDirection = "desc",
    limit: LimitQuery = 25,
    offset: OffsetQuery = 0,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """List experiments for the current user."""
    if paginated:
        return await service.list_experiments_page(
            user_id,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
    return await service.list_experiments(user_id)


@router.get("/experiments/{experiment_slug}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Get an experiment by slug."""
    result = await service.get_experiment(user_id, experiment_slug)
    if not result:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.post("/experiments/{experiment_slug}/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def start_run(
    experiment_slug: str,
    data: RunCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Start a run inside an experiment."""
    try:
        return await service.start_run(user_id, experiment_slug, data)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/experiments/{experiment_slug}/runs", response_model=list[RunResponse] | PaginatedResponse[RunResponse])
async def list_runs(
    experiment_slug: str,
    paginated: bool = False,
    search: SearchQuery = None,
    sort_by: str = "run_number",
    sort_dir: SortDirection = "desc",
    limit: LimitQuery = 25,
    offset: OffsetQuery = 0,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """List runs in an experiment."""
    try:
        if paginated:
            return await service.list_runs_page(
                user_id,
                experiment_slug,
                search=search,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            )
        return await service.list_runs(user_id, experiment_slug)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/experiments/{experiment_slug}/runs/{run_number}", response_model=RunResponse)
async def get_run(
    experiment_slug: str,
    run_number: int,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Get a run by its public identity."""
    result = await service.get_run(user_id, experiment_slug, run_number)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@router.post("/experiments/{experiment_slug}/runs/{run_number}/steps")
async def append_run_steps(
    experiment_slug: str,
    run_number: int,
    data: RunStepBatchCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Append or overwrite logged metrics for a run."""
    try:
        await service.append_run_steps(user_id, experiment_slug, run_number, data)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentTrackingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ExperimentTrackingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/experiments/{experiment_slug}/runs/{run_number}:complete", response_model=RunResponse)
async def complete_run(
    experiment_slug: str,
    run_number: int,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Transition a run to COMPLETED."""
    try:
        return await service.complete_run(user_id, experiment_slug, run_number)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentTrackingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/experiments/{experiment_slug}/runs/{run_number}:fail", response_model=RunResponse)
async def fail_run(
    experiment_slug: str,
    run_number: int,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Transition a run to FAILED."""
    try:
        return await service.fail_run(user_id, experiment_slug, run_number)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentTrackingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/experiments/{experiment_slug}/metrics", response_model=ExperimentMetricsResponse)
async def get_metrics(
    experiment_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """List metrics declared by an experiment."""
    try:
        return await service.get_metrics(user_id, experiment_slug)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/experiments/{experiment_slug}/plots/{metric_name}", response_model=ExperimentMetricResponse)
async def get_experiment_metric_plot(
    experiment_slug: str,
    metric_name: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Get a metric comparison plot across runs."""
    try:
        return await service.get_experiment_metric_plot(user_id, experiment_slug, metric_name)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentTrackingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/experiments/{experiment_slug}/runs/{run_number}/plots/{metric_name}",
    response_model=RunMetricResponse,
)
async def get_run_metric_plot(
    experiment_slug: str,
    run_number: int,
    metric_name: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Get a metric plot for a single run."""
    try:
        return await service.get_run_metric_plot(user_id, experiment_slug, run_number, metric_name)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentTrackingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/experiments/{experiment_slug}/runs/{run_number}/dashboards",
    response_model=list[RunDashboardResponse],
)
async def list_run_dashboards(
    experiment_slug: str,
    run_number: int,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """List saved dashboards for a run."""
    try:
        return await service.list_run_dashboards(user_id, experiment_slug, run_number)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/experiments/{experiment_slug}/runs/{run_number}/dashboards",
    response_model=RunDashboardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_run_dashboard(
    experiment_slug: str,
    run_number: int,
    data: RunDashboardCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Create a saved run dashboard."""
    try:
        return await service.create_run_dashboard(user_id, experiment_slug, run_number, data)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentTrackingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/experiments/{experiment_slug}/runs/{run_number}/dashboards/{dashboard_id}",
    response_model=RunDashboardResponse,
)
async def update_run_dashboard(
    experiment_slug: str,
    run_number: int,
    dashboard_id: uuid.UUID,
    data: RunDashboardUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Update a saved run dashboard."""
    try:
        return await service.update_run_dashboard(user_id, experiment_slug, run_number, dashboard_id, data)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentTrackingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/experiments/{experiment_slug}/runs/{run_number}/dashboards/{dashboard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_run_dashboard(
    experiment_slug: str,
    run_number: int,
    dashboard_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """Delete a saved run dashboard."""
    try:
        await service.delete_run_dashboard(user_id, experiment_slug, run_number, dashboard_id)
    except ExperimentTrackingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return None
