"""
Core ports (interfaces) for repository abstractions.

These define the contracts that infrastructure adapters must implement.
The application layer depends ONLY on these interfaces, never on concrete implementations.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from src.core.entities.resource import Resource
from src.core.entities.experiment_tracking import Experiment, Run, RunStep
from src.core.entities.model_repository import ModelRepository
from src.core.entities.model import Model
from src.core.entities.dataset import Dataset
from src.core.entities.api_key import ApiKey


class ResourceRepository(ABC):
    """Port for resource (metadata) persistence."""

    @abstractmethod
    async def create(self, resource: Resource) -> Resource:
        ...

    @abstractmethod
    async def get_by_id(self, resource_id: uuid.UUID) -> Optional[Resource]:
        ...

    @abstractmethod
    async def update_labels(self, resource_id: uuid.UUID, labels: dict) -> Optional[Resource]:
        ...


class ModelRepositoryRepo(ABC):
    """Port for model repository persistence."""

    @abstractmethod
    async def create(self, repo: ModelRepository) -> ModelRepository:
        ...

    @abstractmethod
    async def get_by_slug(self, user_id: uuid.UUID, slug: str) -> Optional[ModelRepository]:
        ...

    @abstractmethod
    async def get_by_id(self, repository_id: uuid.UUID) -> Optional[ModelRepository]:
        ...

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[ModelRepository]:
        ...

    @abstractmethod
    async def soft_delete(self, user_id: uuid.UUID, slug: str) -> bool:
        ...

    @abstractmethod
    async def slug_exists(self, user_id: uuid.UUID, slug: str) -> bool:
        ...


class ModelRepo(ABC):
    """Port for model (versioned artifact) persistence."""

    @abstractmethod
    async def create(self, model: Model) -> Model:
        ...

    @abstractmethod
    async def get_by_version(self, repository_id: uuid.UUID, version: str) -> Optional[Model]:
        ...

    @abstractmethod
    async def list_by_repository(self, repository_id: uuid.UUID) -> list[Model]:
        ...

    @abstractmethod
    async def update_s3_uri(self, model_id: uuid.UUID, s3_uri: str) -> Optional[Model]:
        ...

    @abstractmethod
    async def get_ready_by_version(self, repository_id: uuid.UUID, version: str) -> Optional[Model]:
        ...

    @abstractmethod
    async def mark_ready(self, model_id: uuid.UUID) -> Optional[Model]:
        ...

    @abstractmethod
    async def get_by_run_id(self, run_id: uuid.UUID) -> Optional[Model]:
        ...


class ExperimentRepo(ABC):
    """Port for experiment persistence."""

    @abstractmethod
    async def create(self, experiment: Experiment) -> Experiment:
        ...

    @abstractmethod
    async def get_by_slug(self, user_id: uuid.UUID, slug: str) -> Optional[Experiment]:
        ...

    @abstractmethod
    async def get_by_id(self, experiment_id: uuid.UUID) -> Optional[Experiment]:
        ...

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[Experiment]:
        ...

    @abstractmethod
    async def slug_exists(self, user_id: uuid.UUID, slug: str) -> bool:
        ...


class RunRepo(ABC):
    """Port for run persistence."""

    @abstractmethod
    async def create(self, run: Run) -> Run:
        ...

    @abstractmethod
    async def get_by_number(self, experiment_id: uuid.UUID, number: int) -> Optional[Run]:
        ...

    @abstractmethod
    async def get_by_id(self, run_id: uuid.UUID) -> Optional[Run]:
        ...

    @abstractmethod
    async def list_by_experiment(self, experiment_id: uuid.UUID) -> list[Run]:
        ...

    @abstractmethod
    async def get_next_number(self, experiment_id: uuid.UUID) -> int:
        ...

    @abstractmethod
    async def update_status(self, run_id: uuid.UUID, status: str, ended_at: datetime | None = None) -> Optional[Run]:
        ...


class RunStepRepo(ABC):
    """Port for run-step persistence."""

    @abstractmethod
    async def upsert_batch(self, steps: list[RunStep]) -> None:
        ...

    @abstractmethod
    async def get_latest_for_run(self, run_id: uuid.UUID) -> Optional[RunStep]:
        ...

    @abstractmethod
    async def list_by_run(self, run_id: uuid.UUID) -> list[RunStep]:
        ...


class DatasetRepo(ABC):
    """Port for dataset persistence."""

    @abstractmethod
    async def create(self, dataset: Dataset) -> Dataset:
        ...

    @abstractmethod
    async def get_latest_by_name(self, name: str, user_id: uuid.UUID) -> Optional[Dataset]:
        ...

    @abstractmethod
    async def get_by_id(self, dataset_id: uuid.UUID) -> Optional[Dataset]:
        ...

    @abstractmethod
    async def get_by_slug_and_version(self, slug: str, user_id: uuid.UUID, version: int) -> Optional[Dataset]:
        ...

    @abstractmethod
    async def get_latest_ready(self, slug: str, user_id: uuid.UUID) -> Optional[Dataset]:
        ...

    @abstractmethod
    async def get_ready_by_slug_and_version(self, slug: str, user_id: uuid.UUID, version: int) -> Optional[Dataset]:
        ...

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[Dataset]:
        ...

    @abstractmethod
    async def mark_ready(self, slug: str, user_id: uuid.UUID, version: int, s3_uri: str) -> Optional[Dataset]:
        ...

    @abstractmethod
    async def get_next_version(self, slug: str, user_id: uuid.UUID) -> int:
        ...

    @abstractmethod
    async def slug_exists(self, slug: str, user_id: uuid.UUID) -> bool:
        ...


class ApiKeyRepo(ABC):
    """Port for API key persistence."""

    @abstractmethod
    async def create(self, api_key: ApiKey) -> ApiKey:
        ...

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[ApiKey]:
        ...

    @abstractmethod
    async def get_by_prefix(self, prefix: str) -> Optional[ApiKey]:
        ...

    @abstractmethod
    async def prefix_exists(self, prefix: str) -> bool:
        ...

    @abstractmethod
    async def name_exists(self, user_id: uuid.UUID, name: str) -> bool:
        ...

    @abstractmethod
    async def revoke(self, user_id: uuid.UUID, name: str) -> bool:
        ...
