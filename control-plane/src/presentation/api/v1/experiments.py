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


@router.get("/experiments", response_model=list[ExperimentResponse])
async def list_experiments(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """List experiments for the current user."""
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


@router.get("/experiments/{experiment_slug}/runs", response_model=list[RunResponse])
async def list_runs(
    experiment_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
):
    """List runs in an experiment."""
    try:
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
