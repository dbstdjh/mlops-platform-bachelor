"""Presentation layer: Model deployment API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.deployment_service import DeploymentService
from src.core.entities.dashboard import (
    DeploymentDashboardCreate,
    DeploymentDashboardResponse,
    DeploymentPlotField,
)
from src.core.entities.deployment import DeploymentCreate, DeploymentResponse
from src.core.entities.pagination import PaginatedResponse, SortDirection
from src.presentation.api.v1.pagination import LimitQuery, OffsetQuery, SearchQuery
from src.presentation.dependencies import get_current_user_id, get_deployment_service

router = APIRouter()


@router.post(
    "/repositories/{repository_slug}/models/{version}/deployments",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_model_deployment(
    repository_slug: str,
    version: str,
    data: DeploymentCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """Create an asynchronous deployment for a READY model version."""
    try:
        return await service.create_model_deployment(user_id, repository_slug, version, data)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/deployments", response_model=list[DeploymentResponse] | PaginatedResponse[DeploymentResponse])
async def list_deployments(
    paginated: bool = False,
    search: SearchQuery = None,
    sort_by: str = "created_at",
    sort_dir: SortDirection = "desc",
    limit: LimitQuery = 25,
    offset: OffsetQuery = 0,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """List deployments for the current user."""
    if paginated:
        return await service.list_deployments_page(
            user_id,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
    return await service.list_deployments(user_id)


@router.get("/deployments/{deployment_slug}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """Get a deployment by public slug."""
    result = await service.get_deployment(user_id, deployment_slug)
    if not result:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return result


@router.get(
    "/deployments/{deployment_slug}/dashboards",
    response_model=list[DeploymentDashboardResponse],
)
async def list_deployment_dashboards(
    deployment_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """List Grafana-backed observability panels for a deployment."""
    try:
        return await service.list_deployment_dashboards(user_id, deployment_slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/deployments/{deployment_slug}/dashboards",
    response_model=DeploymentDashboardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_deployment_dashboard(
    deployment_slug: str,
    data: DeploymentDashboardCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """Create a custom Grafana-backed observability panel for a deployment."""
    try:
        return await service.create_deployment_dashboard(user_id, deployment_slug, data)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Deployment not found" else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.delete(
    "/deployments/{deployment_slug}/dashboards/{dashboard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_deployment_dashboard(
    deployment_slug: str,
    dashboard_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """Delete a custom deployment observability panel."""
    try:
        await service.delete_deployment_dashboard(user_id, deployment_slug, dashboard_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get(
    "/deployments/{deployment_slug}/plot-fields",
    response_model=list[DeploymentPlotField],
)
async def list_deployment_plot_fields(
    deployment_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """List numeric input/output fields available for custom deployment plots."""
    try:
        return await service.list_plot_fields(user_id, deployment_slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/deployments/{deployment_slug}:purge",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def purge_deployment(
    deployment_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """Permanently remove a deployment record from the control plane."""
    deleted = await service.purge_deployment(user_id, deployment_slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Deployment not found")


@router.delete(
    "/deployments/{deployment_slug}",
    response_model=DeploymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_deployment(
    deployment_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DeploymentService = Depends(get_deployment_service),
):
    """Enqueue asynchronous deployment deletion."""
    result = await service.delete_deployment(user_id, deployment_slug)
    if not result:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return result
