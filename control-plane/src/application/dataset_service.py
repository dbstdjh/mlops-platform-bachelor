"""
Application service: Feature Registry (Dataset management).

Orchestrates the dataset upload/download lifecycle using pre-signed URLs.
Depends only on core ports — never on infrastructure directly.
"""

import uuid
from pathlib import PurePosixPath

from src.core.entities.dataset import (
    Dataset,
    DatasetCreate,
    DatasetResponse,
    DatasetUploadResponse,
)
from src.core.entities.resource import Resource
from src.core.ports.repositories import DatasetRepo, ResourceRepository
from src.core.slugging import slug_candidate, slugify
from src.core.ports.storage import StoragePort

DATASETS_BUCKET = "datasets"


class DatasetService:
    """Application service for dataset lifecycle management."""

    def __init__(
        self,
        dataset_repo: DatasetRepo,
        resource_repo: ResourceRepository,
        storage: StoragePort,
    ):
        self._dataset_repo = dataset_repo
        self._resource_repo = resource_repo
        self._storage = storage

    async def initiate_upload(self, user_id: uuid.UUID, data: DatasetCreate) -> DatasetUploadResponse:
        """
        Step 1 of the push workflow:
        Create a PENDING dataset record and return a pre-signed upload URL.
        The SDK will use this URL to stream the file directly to MinIO.
        """
        existing = await self._dataset_repo.get_latest_by_name(data.name, user_id)
        slug = existing.slug if existing else await self._generate_unique_slug(user_id, data.name)
        version = await self._dataset_repo.get_next_version(slug, user_id)

        # Create the resource (metadata container)
        resource = Resource(labels=data.labels)
        await self._resource_repo.create(resource)

        # Build the S3 object path
        object_name = f"{user_id}/{slug}/v{version}.{data.file_type}"

        # Create the PENDING dataset record
        dataset = Dataset(
            user_id=user_id,
            resource_id=resource.id,
            name=data.name,
            slug=slug,
            s3_uri=f"s3://{DATASETS_BUCKET}/{object_name}",
            status="PENDING",
            version=version,
            file_type=data.file_type,
        )
        await self._dataset_repo.create(dataset)

        # Generate a pre-signed upload URL
        upload_url = await self._storage.generate_upload_url(DATASETS_BUCKET, object_name)

        return DatasetUploadResponse(
            dataset_slug=dataset.slug,
            upload_url=upload_url,
            version=version,
        )

    async def confirm_upload(self, object_key: str) -> bool:
        """
        Step 2 of the push workflow (called by MinIO webhook):
        Mark the dataset as READY after the file has been successfully uploaded.
        The object_key comes from the S3 event notification payload.
        """
        s3_uri = f"s3://{DATASETS_BUCKET}/{object_key}"

        parts = PurePosixPath(object_key).parts
        if len(parts) != 3:
            return False

        try:
            user_id = uuid.UUID(parts[0])
        except ValueError:
            return False

        slug = parts[1]
        version_part = PurePosixPath(parts[2]).stem
        if not version_part.startswith("v"):
            return False
        try:
            version = int(version_part.removeprefix("v"))
        except ValueError:
            return False

        updated = await self._dataset_repo.mark_ready(slug, user_id, version, s3_uri)
        return updated is not None

    async def get_download_url(self, user_id: uuid.UUID, slug: str) -> str | None:
        """
        Pull workflow: Get a pre-signed download URL for the latest READY version.
        """
        dataset = await self._dataset_repo.get_latest_ready(slug, user_id)
        if not dataset or not dataset.s3_uri:
            return None

        # Extract object name from s3_uri
        object_name = dataset.s3_uri.replace(f"s3://{DATASETS_BUCKET}/", "")
        return await self._storage.generate_download_url(DATASETS_BUCKET, object_name)

    async def get_version_download_url(self, user_id: uuid.UUID, slug: str, version: int) -> str | None:
        """Get a pre-signed download URL for a specific READY dataset version."""
        dataset = await self._dataset_repo.get_ready_by_slug_and_version(slug, user_id, version)
        if not dataset or not dataset.s3_uri:
            return None

        object_name = dataset.s3_uri.replace(f"s3://{DATASETS_BUCKET}/", "")
        return await self._storage.generate_download_url(DATASETS_BUCKET, object_name)

    async def get_dataset(self, user_id: uuid.UUID, slug: str, version: int) -> DatasetResponse | None:
        """Get a dataset version by slug and version with its resource labels."""
        dataset = await self._dataset_repo.get_by_slug_and_version(slug, user_id, version)
        if not dataset:
            return None

        return await self._build_dataset_response(dataset)

    async def list_datasets(self, user_id: uuid.UUID) -> list[DatasetResponse]:
        """List all datasets for a user."""
        datasets = await self._dataset_repo.list_by_user(user_id)
        responses = []
        for dataset in datasets:
            responses.append(await self._build_dataset_response(dataset))
        return responses

    async def _build_dataset_response(self, dataset: Dataset) -> DatasetResponse:
        resource = await self._resource_repo.get_by_id(dataset.resource_id)
        labels = resource.labels if resource else {}
        return DatasetResponse(
            name=dataset.name,
            slug=dataset.slug,
            version=dataset.version,
            status=dataset.status,
            file_type=dataset.file_type,
            created_at=dataset.created_at,
            labels=labels,
        )

    async def _generate_unique_slug(self, user_id: uuid.UUID, name: str) -> str:
        base_slug = slugify(name)
        index = 1
        while True:
            candidate = slug_candidate(base_slug, index)
            if not await self._dataset_repo.slug_exists(candidate, user_id):
                return candidate
            index += 1
