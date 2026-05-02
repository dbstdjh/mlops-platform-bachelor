"""
Presentation layer: Feature Registry (Dataset) API routes.
"""

import uuid
from urllib.parse import unquote_plus

from fastapi import APIRouter, Depends, HTTPException, Request

from src.application.dataset_service import DatasetService
from src.core.entities.dataset import (
    DatasetCreate,
    DatasetResponse,
    DatasetUploadResponse,
)
from src.core.entities.pagination import PaginatedResponse, SortDirection
from src.presentation.dependencies import get_dataset_service, get_current_user_id
from src.presentation.api.v1.pagination import LimitQuery, OffsetQuery, SearchQuery

router = APIRouter()


@router.post("/datasets:upload", response_model=DatasetUploadResponse, status_code=201)
async def initiate_dataset_upload(
    data: DatasetCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DatasetService = Depends(get_dataset_service),
):
    """
    Initiate a dataset upload.
    Returns a pre-signed URL for the SDK to stream the file directly to MinIO.
    """
    return await service.initiate_upload(user_id, data)


@router.post("/datasets:confirm_upload")
async def confirm_dataset_upload(
    request: Request,
    service: DatasetService = Depends(get_dataset_service),
):
    """
    MinIO webhook endpoint — called when a file is uploaded to the 'datasets' bucket.
    Marks the dataset as READY.
    """
    try:
        payload = await request.json()
        records = payload.get("Records", [])
        for record in records:
            object_key = unquote_plus(record.get("s3", {}).get("object", {}).get("key", ""))
            if object_key:
                await service.confirm_upload(object_key)
        return {"status": "ok"}
    except Exception as exc:
        # Webhooks must return 200 to avoid MinIO retries flooding logs
        return {"status": "error", "detail": str(exc)}


@router.get("/datasets/{dataset_slug}:download")
async def get_download_url(
    dataset_slug: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DatasetService = Depends(get_dataset_service),
):
    """Get a pre-signed download URL for the latest READY version of a dataset."""
    url = await service.get_download_url(user_id, dataset_slug)
    if not url:
        raise HTTPException(status_code=404, detail="No ready dataset found with that slug")
    return {"download_url": url}


@router.get("/datasets/{dataset_slug}/versions/{version}:download")
async def get_version_download_url(
    dataset_slug: str,
    version: int,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DatasetService = Depends(get_dataset_service),
):
    """Get a pre-signed download URL for a specific READY dataset version."""
    url = await service.get_version_download_url(user_id, dataset_slug, version)
    if not url:
        raise HTTPException(status_code=404, detail="No ready dataset found for that slug and version")
    return {"download_url": url}


@router.get("/datasets/{dataset_slug}/versions/{version}", response_model=DatasetResponse)
async def get_dataset(
    dataset_slug: str,
    version: int,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DatasetService = Depends(get_dataset_service),
):
    """Get a dataset version by slug and version."""
    result = await service.get_dataset(user_id, dataset_slug, version)
    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.get("/datasets", response_model=list[DatasetResponse] | PaginatedResponse[DatasetResponse])
async def list_datasets(
    paginated: bool = False,
    search: SearchQuery = None,
    sort_by: str = "created_at",
    sort_dir: SortDirection = "desc",
    limit: LimitQuery = 25,
    offset: OffsetQuery = 0,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DatasetService = Depends(get_dataset_service),
):
    """List all datasets for the current user."""
    if paginated:
        return await service.list_datasets_page(
            user_id,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
    return await service.list_datasets(user_id)
