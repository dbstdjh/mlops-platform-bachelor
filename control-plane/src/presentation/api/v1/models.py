"""
Presentation layer: Model Versioning & Registry API routes.
"""

import uuid
from urllib.parse import unquote_plus

from fastapi import APIRouter, Depends, HTTPException, Request

from src.application.model_registry_service import ModelRegistryService
from src.core.entities.model import ModelCreate, ModelResponse, ModelUploadRequest, ModelUploadResponse
from src.core.entities.model_repository import (
    ModelRepositoryCreate,
    ModelRepositoryResponse,
)
from src.presentation.dependencies import get_model_registry_service, get_current_user_id

router = APIRouter()


# --- Model Repository endpoints ---

@router.post("/repositories", response_model=ModelRepositoryResponse, status_code=201)
async def create_repository(
    data: ModelRepositoryCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """Create a new model repository."""
    return await service.create_repository(user_id, data)


@router.get("/repositories", response_model=list[ModelRepositoryResponse])
async def list_repositories(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """List all model repositories for the current user."""
    return await service.list_repositories(user_id)


@router.get("/repositories/{repository_slug}", response_model=ModelRepositoryResponse)
async def get_repository(
    repository_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """Get a model repository by slug."""
    result = await service.get_repository(user_id, repository_slug)
    if not result:
        raise HTTPException(status_code=404, detail="Repository not found")
    return result


@router.delete("/repositories/{repository_slug}", status_code=204)
async def delete_repository(
    repository_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """Soft-delete a model repository."""
    success = await service.delete_repository(user_id, repository_slug)
    if not success:
        raise HTTPException(status_code=404, detail="Repository not found")


# --- Model Version endpoints ---

@router.post("/repositories/{repository_slug}/models", response_model=ModelResponse, status_code=201)
async def create_model(
    repository_slug: str,
    data: ModelCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """Create a new model version within a repository."""
    try:
        return await service.create_model(user_id, repository_slug, data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/repositories/{repository_slug}/models", response_model=list[ModelResponse])
async def list_models(
    repository_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """List all model versions within a repository."""
    try:
        return await service.list_models(user_id, repository_slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/repositories/{repository_slug}/models/{version}:download")
async def get_model_download_url(
    repository_slug: str,
    version: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """Get a pre-signed download URL for a READY model artifact."""
    url = await service.get_download_url(user_id, repository_slug, version)
    if not url:
        raise HTTPException(status_code=404, detail="No ready model found with that version")
    return {"download_url": url}


@router.post("/repositories/{repository_slug}/models/{version}:upload", response_model=ModelUploadResponse)
async def get_model_upload_url(
    repository_slug: str,
    version: str,
    data: ModelUploadRequest | None = None,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """Get a pre-signed upload URL for model weights."""
    try:
        result = await service.get_upload_url(
            user_id,
            repository_slug,
            version,
            file_name=None if data is None else data.file_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")
    return result


@router.post("/repositories/{repository_slug}/models/{version}:confirm_upload")
async def confirm_model_upload(
    repository_slug: str,
    version: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """Confirm that the model artifact exists in storage and mark it READY."""
    try:
        confirmed = await service.confirm_upload(user_id, repository_slug, version)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not confirmed:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"status": "ok"}


@router.post("/models:confirm_upload")
async def confirm_model_upload_webhook(
    request: Request,
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """MinIO webhook endpoint for model uploads."""
    try:
        payload = await request.json()
        records = payload.get("Records", [])
        for record in records:
            object_key = unquote_plus(record.get("s3", {}).get("object", {}).get("key", ""))
            if object_key:
                await service.confirm_upload_from_object_key(object_key)
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/repositories/{repository_slug}/models/{version}", response_model=ModelResponse)
async def get_model(
    repository_slug: str,
    version: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ModelRegistryService = Depends(get_model_registry_service),
):
    """Get a model by repository slug and version."""
    result = await service.get_model(user_id, repository_slug, version)
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")
    return result
