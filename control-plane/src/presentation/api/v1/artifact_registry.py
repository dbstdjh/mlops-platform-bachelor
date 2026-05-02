"""Presentation layer: Artifact Registry API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.artifact_registry_service import ArtifactRegistryService
from src.core.entities.artifact_registry import (
    ArtifactImage,
    ArtifactImageDeploymentCreate,
    ArtifactRegistryStatus,
    RegistryTokenCreate,
    RegistryTokenIssuedResponse,
    RegistryTokenResponse,
)
from src.core.entities.deployment import DeploymentResponse
from src.core.entities.pagination import PaginatedResponse, SortDirection
from src.infrastructure.artifact_registry.gitea import GiteaRegistryError
from src.infrastructure.database.models import UserORM
from src.presentation.api.v1.pagination import LimitQuery, OffsetQuery, SearchQuery
from src.presentation.dependencies import (
    get_artifact_registry_service,
    get_current_user,
    get_current_user_id,
)

router = APIRouter()


@router.get("/artifact-registry/status", response_model=ArtifactRegistryStatus)
async def get_artifact_registry_status(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ArtifactRegistryService = Depends(get_artifact_registry_service),
):
    """Return the current user's custom image registry status."""
    return await service.get_status(user_id)


@router.post("/artifact-registry:enable", response_model=ArtifactRegistryStatus)
async def enable_artifact_registry(
    user: UserORM = Depends(get_current_user),
    service: ArtifactRegistryService = Depends(get_artifact_registry_service),
):
    """Enable and provision custom image registry access for the current user."""
    try:
        return await service.enable(user.id, user.email)
    except GiteaRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/artifact-registry/tokens", response_model=list[RegistryTokenResponse])
async def list_artifact_registry_tokens(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ArtifactRegistryService = Depends(get_artifact_registry_service),
):
    """List user-managed Docker registry tokens."""
    try:
        return await service.list_tokens(user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except GiteaRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/artifact-registry/tokens",
    response_model=RegistryTokenIssuedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_artifact_registry_token(
    data: RegistryTokenCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ArtifactRegistryService = Depends(get_artifact_registry_service),
):
    """Create a Docker registry token and return plaintext once."""
    try:
        return await service.create_token(user_id, data)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GiteaRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/artifact-registry/tokens/{token_name}:revoke")
async def revoke_artifact_registry_token(
    token_name: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ArtifactRegistryService = Depends(get_artifact_registry_service),
):
    """Revoke a user-managed Docker registry token."""
    try:
        revoked = await service.revoke_token(user_id, token_name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except GiteaRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not revoked:
        raise HTTPException(status_code=404, detail="Registry token not found")
    return {"status": "ok"}


@router.get("/artifact-registry/images", response_model=list[ArtifactImage] | PaginatedResponse[ArtifactImage])
async def list_artifact_registry_images(
    paginated: bool = False,
    search: SearchQuery = None,
    sort_by: str = "created_at",
    sort_dir: SortDirection = "desc",
    limit: LimitQuery = 25,
    offset: OffsetQuery = 0,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ArtifactRegistryService = Depends(get_artifact_registry_service),
):
    """List custom container images pushed by the current user."""
    try:
        if paginated:
            return await service.list_images_page(
                user_id,
                search=search,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            )
        return await service.list_images(user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except GiteaRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/artifact-registry/images/{image_name}/tags/{tag}/deployments",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_artifact_image_deployment(
    image_name: str,
    tag: str,
    data: ArtifactImageDeploymentCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ArtifactRegistryService = Depends(get_artifact_registry_service),
):
    """Create an asynchronous deployment for a custom image tag."""
    try:
        return await service.create_image_deployment(user_id, image_name, tag, data)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GiteaRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
