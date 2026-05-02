"""Presentation layer: dashboard overview API routes."""

import uuid

from fastapi import APIRouter, Depends

from src.application.dataset_service import DatasetService
from src.application.deployment_service import DeploymentService
from src.application.experiment_tracking_service import ExperimentTrackingService
from src.application.model_registry_service import ModelRegistryService
from src.core.entities.overview import OverviewRecentResponse, OverviewSummaryResponse
from src.presentation.dependencies import (
    get_current_user_id,
    get_dataset_service,
    get_deployment_service,
    get_experiment_tracking_service,
    get_model_registry_service,
)

router = APIRouter()


@router.get("/overview/summary", response_model=OverviewSummaryResponse)
async def get_overview_summary(
    user_id: uuid.UUID = Depends(get_current_user_id),
    experiment_service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
    dataset_service: DatasetService = Depends(get_dataset_service),
    model_service: ModelRegistryService = Depends(get_model_registry_service),
    deployment_service: DeploymentService = Depends(get_deployment_service),
):
    """Return dashboard overview counts without fetching full resource lists."""
    experiments = await experiment_service.list_experiments_page(
        user_id, search=None, sort_by="created_at", sort_dir="desc", limit=1, offset=0
    )
    datasets = await dataset_service.list_datasets_page(
        user_id, search=None, sort_by="created_at", sort_dir="desc", limit=1, offset=0
    )
    repositories = await model_service.list_repositories_page(
        user_id, search=None, sort_by="created_at", sort_dir="desc", limit=1, offset=0
    )
    deployments = await deployment_service.list_deployments_page(
        user_id, search=None, sort_by="created_at", sort_dir="desc", limit=1, offset=0
    )
    return OverviewSummaryResponse(
        experiment_count=experiments.total,
        dataset_count=datasets.total,
        repository_count=repositories.total,
        deployment_count=deployments.total,
    )


@router.get("/overview/recent", response_model=OverviewRecentResponse)
async def get_overview_recent(
    user_id: uuid.UUID = Depends(get_current_user_id),
    experiment_service: ExperimentTrackingService = Depends(get_experiment_tracking_service),
    dataset_service: DatasetService = Depends(get_dataset_service),
    model_service: ModelRegistryService = Depends(get_model_registry_service),
    deployment_service: DeploymentService = Depends(get_deployment_service),
):
    """Return recent resources for the dashboard overview."""
    experiments = await experiment_service.list_experiments_page(
        user_id, search=None, sort_by="created_at", sort_dir="desc", limit=3, offset=0
    )
    datasets = await dataset_service.list_datasets_page(
        user_id, search=None, sort_by="created_at", sort_dir="desc", limit=12, offset=0
    )
    repositories = await model_service.list_repositories_page(
        user_id, search=None, sort_by="created_at", sort_dir="desc", limit=3, offset=0
    )
    deployments = await deployment_service.list_deployments_page(
        user_id, search=None, sort_by="created_at", sort_dir="desc", limit=3, offset=0
    )
    return OverviewRecentResponse(
        experiments=experiments.items,
        datasets=datasets.items,
        repositories=repositories.items,
        deployments=deployments.items,
    )
