"""
Application service: Model Versioning & Registry.

Manages model repositories and versioned model artifacts.
Depends only on core ports — never on infrastructure directly.
"""

import uuid
from pathlib import PurePosixPath

from src.core.entities.experiment_tracking import RunRef
from src.core.entities.model import Model, ModelCreate, ModelResponse, ModelUploadResponse
from src.core.entities.model_repository import (
    ModelRepository,
    ModelRepositoryCreate,
    ModelRepositoryResponse,
)
from src.core.entities.resource import Resource
from src.core.ports.repositories import (
    ExperimentRepo,
    ModelRepo,
    ModelRepositoryRepo,
    ResourceRepository,
    RunRepo,
)
from src.core.ports.storage import StoragePort
from src.core.slugging import slug_candidate, slugify

MODELS_BUCKET = "models"


class ModelRegistryService:
    """Application service for model repository and model version management."""

    def __init__(
        self,
        model_repo_repo: ModelRepositoryRepo,
        model_repo: ModelRepo,
        resource_repo: ResourceRepository,
        experiment_repo: ExperimentRepo,
        run_repo: RunRepo,
        storage: StoragePort,
    ):
        self._model_repo_repo = model_repo_repo
        self._model_repo = model_repo
        self._resource_repo = resource_repo
        self._experiment_repo = experiment_repo
        self._run_repo = run_repo
        self._storage = storage

    # --- Model Repository CRUD ---

    async def create_repository(self, user_id: uuid.UUID, data: ModelRepositoryCreate) -> ModelRepositoryResponse:
        """Create a new model repository."""
        slug = await self._generate_unique_slug(user_id, data.name)
        resource = Resource(labels=data.labels)
        await self._resource_repo.create(resource)

        repo = ModelRepository(
            user_id=user_id,
            resource_id=resource.id,
            name=data.name,
            slug=slug,
        )
        await self._model_repo_repo.create(repo)

        return await self._build_repository_response(repo)

    async def get_repository(self, user_id: uuid.UUID, repo_slug: str) -> ModelRepositoryResponse | None:
        """Get a model repository by slug."""
        repo = await self._model_repo_repo.get_by_slug(user_id, repo_slug)
        if not repo:
            return None

        return await self._build_repository_response(repo)

    async def list_repositories(self, user_id: uuid.UUID) -> list[ModelRepositoryResponse]:
        """List all model repositories for a user."""
        repos = await self._model_repo_repo.list_by_user(user_id)
        responses = []
        for repo in repos:
            responses.append(await self._build_repository_response(repo))
        return responses

    async def delete_repository(self, user_id: uuid.UUID, repo_slug: str) -> bool:
        """Soft-delete a model repository."""
        return await self._model_repo_repo.soft_delete(user_id, repo_slug)

    # --- Model Version CRUD ---

    async def create_model(self, user_id: uuid.UUID, repo_slug: str, data: ModelCreate) -> ModelResponse:
        """Create a new model version within a repository."""
        # Verify the repository exists
        repo = await self._model_repo_repo.get_by_slug(user_id, repo_slug)
        if not repo:
            raise ValueError(f"Model repository '{repo_slug}' not found")

        resource = Resource(labels=data.labels)
        await self._resource_repo.create(resource)

        model = Model(
            resource_id=resource.id,
            repository_id=repo.id,
            run_id=await self._resolve_run_id(user_id, data.run),
            name=data.name,
            version=data.version,
            status="PENDING",
        )
        await self._model_repo.create(model)

        return await self._build_model_response(model, repo)

    async def get_model(self, user_id: uuid.UUID, repo_slug: str, version: str) -> ModelResponse | None:
        """Get a model version by repository slug and version."""
        repo = await self._model_repo_repo.get_by_slug(user_id, repo_slug)
        if not repo:
            return None

        model = await self._model_repo.get_by_version(repo.id, version)
        if not model:
            return None

        return await self._build_model_response(model, repo)

    async def list_models(self, user_id: uuid.UUID, repo_slug: str) -> list[ModelResponse]:
        """List all models within a repository."""
        repo = await self._model_repo_repo.get_by_slug(user_id, repo_slug)
        if not repo:
            raise ValueError(f"Model repository '{repo_slug}' not found")

        models = await self._model_repo.list_by_repository(repo.id)
        responses = []
        for model in models:
            responses.append(await self._build_model_response(model, repo))
        return responses

    async def get_upload_url(self, user_id: uuid.UUID, repo_slug: str, version: str) -> ModelUploadResponse | None:
        """Generate a pre-signed upload URL for model weights."""
        repo = await self._model_repo_repo.get_by_slug(user_id, repo_slug)
        if not repo:
            return None

        model = await self._model_repo.get_by_version(repo.id, version)
        if not model:
            return None

        # Build the S3 object path
        object_name = f"{repo.user_id}/{repo.slug}/{model.name}/v{model.version}"
        upload_url = await self._storage.generate_upload_url(MODELS_BUCKET, object_name)

        s3_uri = f"s3://{MODELS_BUCKET}/{object_name}"
        await self._model_repo.update_s3_uri(model.id, s3_uri)

        return ModelUploadResponse(repository_slug=repo.slug, version=model.version, upload_url=upload_url)

    async def confirm_upload(self, user_id: uuid.UUID, repo_slug: str, version: str) -> bool:
        """Mark a model artifact as READY after the client uploads it to MinIO."""
        repo = await self._model_repo_repo.get_by_slug(user_id, repo_slug)
        if not repo:
            return False

        model = await self._model_repo.get_by_version(repo.id, version)
        if not model:
            return False
        if not model.s3_uri:
            raise ValueError("Model upload has not been initiated")

        object_name = self._object_name_from_s3_uri(model.s3_uri)
        if not await self._storage.object_exists(MODELS_BUCKET, object_name):
            raise ValueError("Uploaded model artifact not found in storage")

        return await self._mark_model_ready(model, object_name)

    async def confirm_upload_from_object_key(self, object_key: str) -> bool:
        """Mark a model artifact as READY from a MinIO S3 event object key."""
        parts = PurePosixPath(object_key).parts
        if len(parts) != 4:
            return False

        try:
            user_id = uuid.UUID(parts[0])
        except ValueError:
            return False

        repo_slug = parts[1]
        model_name = parts[2]
        version_part = PurePosixPath(parts[3]).name
        if not version_part.startswith("v"):
            return False
        version = version_part.removeprefix("v")
        if not version:
            return False

        repo = await self._model_repo_repo.get_by_slug(user_id, repo_slug)
        if not repo:
            return False

        model = await self._model_repo.get_by_version(repo.id, version)
        if not model or model.name != model_name:
            return False

        return await self._mark_model_ready(model, object_key)

    async def get_download_url(self, user_id: uuid.UUID, repo_slug: str, version: str) -> str | None:
        """Generate a pre-signed download URL for a READY model artifact."""
        repo = await self._model_repo_repo.get_by_slug(user_id, repo_slug)
        if not repo:
            return None

        model = await self._model_repo.get_ready_by_version(repo.id, version)
        if not model or not model.s3_uri:
            return None

        object_name = self._object_name_from_s3_uri(model.s3_uri)
        return await self._storage.generate_download_url(MODELS_BUCKET, object_name)

    async def _build_repository_response(self, repo: ModelRepository) -> ModelRepositoryResponse:
        resource = await self._resource_repo.get_by_id(repo.resource_id)
        labels = resource.labels if resource else {}
        return ModelRepositoryResponse(
            name=repo.name,
            slug=repo.slug,
            is_deleted=repo.is_deleted,
            created_at=repo.created_at,
            labels=labels,
        )

    async def _build_model_response(self, model: Model, repo: ModelRepository) -> ModelResponse:
        resource = await self._resource_repo.get_by_id(model.resource_id)
        labels = resource.labels if resource else {}
        return ModelResponse(
            repository_slug=repo.slug,
            name=model.name,
            version=model.version,
            run=await self._build_run_ref(model.run_id),
            is_deleted=model.is_deleted,
            s3_uri=model.s3_uri,
            status=model.status,
            created_at=model.created_at,
            labels=labels,
        )

    def _object_name_from_s3_uri(self, s3_uri: str) -> str:
        parts = PurePosixPath(s3_uri.replace(f"s3://{MODELS_BUCKET}/", "")).parts
        return "/".join(parts)

    async def _mark_model_ready(self, model: Model, object_name: str) -> bool:
        s3_uri = f"s3://{MODELS_BUCKET}/{object_name}"
        await self._model_repo.update_s3_uri(model.id, s3_uri)
        updated = await self._model_repo.mark_ready(model.id)
        return updated is not None

    async def _resolve_run_id(self, user_id: uuid.UUID, run_ref: RunRef | None) -> uuid.UUID | None:
        if run_ref is None:
            return None
        experiment = await self._experiment_repo.get_by_slug(user_id, run_ref.experiment_slug)
        if not experiment:
            raise ValueError(f"Experiment '{run_ref.experiment_slug}' not found")
        run = await self._run_repo.get_by_number(experiment.id, run_ref.run_number)
        if not run:
            raise ValueError(
                f"Run '{run_ref.run_number}' not found in experiment '{run_ref.experiment_slug}'"
            )
        return run.id

    async def _build_run_ref(self, run_id: uuid.UUID | None) -> RunRef | None:
        if run_id is None:
            return None
        run = await self._run_repo.get_by_id(run_id)
        if not run:
            return None
        experiment = await self._experiment_repo.get_by_id(run.experiment_id)
        if not experiment:
            return None
        return RunRef(experiment_slug=experiment.slug, run_number=run.number)

    async def _generate_unique_slug(self, user_id: uuid.UUID, name: str) -> str:
        base_slug = slugify(name)
        index = 1
        while True:
            candidate = slug_candidate(base_slug, index)
            if not await self._model_repo_repo.slug_exists(user_id, candidate):
                return candidate
            index += 1
