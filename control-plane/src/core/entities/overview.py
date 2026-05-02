"""Dashboard overview API contracts."""

from pydantic import BaseModel

from src.core.entities.dataset import DatasetResponse
from src.core.entities.deployment import DeploymentResponse
from src.core.entities.experiment_tracking import ExperimentResponse
from src.core.entities.model_repository import ModelRepositoryResponse


class OverviewSummaryResponse(BaseModel):
    """Compact platform counts for the dashboard overview."""

    experiment_count: int
    dataset_count: int
    repository_count: int
    deployment_count: int


class OverviewRecentResponse(BaseModel):
    """Recent resources shown on the dashboard overview."""

    experiments: list[ExperimentResponse]
    datasets: list[DatasetResponse]
    repositories: list[ModelRepositoryResponse]
    deployments: list[DeploymentResponse]
