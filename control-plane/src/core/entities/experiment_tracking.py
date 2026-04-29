"""
Core domain entities and API contracts for experiment tracking.
"""

import uuid
from datetime import datetime, timezone
from numbers import Real

from pydantic import BaseModel, Field, field_validator, model_validator


class RunRef(BaseModel):
    """Public reference to a run."""

    experiment_slug: str
    run_number: int = Field(ge=1)


class DatasetRef(BaseModel):
    """Public reference to a dataset version."""

    dataset_slug: str
    version: int = Field(ge=1)


class ModelRef(BaseModel):
    """Public reference to a model artifact."""

    repository_slug: str
    version: str


class Experiment(BaseModel):
    """A grouping of related training runs."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    resource_id: uuid.UUID
    name: str
    slug: str
    logged_data_template: list[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Run(BaseModel):
    """A single training execution."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    resource_id: uuid.UUID
    experiment_id: uuid.UUID
    dataset_id: uuid.UUID | None = None
    number: int = Field(ge=1)
    status: str = "RUNNING"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None


class RunStep(BaseModel):
    """Metrics captured for a single run step."""

    run_id: uuid.UUID
    run_step_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    step: int = Field(ge=0)
    logged_data: dict[str, float]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExperimentCreate(BaseModel):
    """Schema for creating an experiment."""

    name: str
    logged_data_template: list[str]
    labels: dict = Field(default_factory=dict, description="Resource metadata labels")

    @field_validator("logged_data_template")
    @classmethod
    def normalize_logged_data_template(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            metric = item.strip()
            if not metric:
                continue
            if metric in seen:
                continue
            seen.add(metric)
            normalized.append(metric)
        if not normalized:
            raise ValueError("logged_data_template must contain at least one metric")
        return normalized


class RunCreate(BaseModel):
    """Schema for starting a run."""

    dataset_slug: str | None = None
    dataset_version: int | None = Field(default=None, ge=1)
    labels: dict = Field(default_factory=dict, description="Resource metadata labels")

    @model_validator(mode="after")
    def validate_dataset_ref(self) -> "RunCreate":
        if self.dataset_slug is None and self.dataset_version is None:
            return self
        if self.dataset_slug is None or self.dataset_version is None:
            raise ValueError("dataset_slug and dataset_version must be provided together")
        return self


class RunStepItemCreate(BaseModel):
    """A single logged metrics payload."""

    step: int = Field(ge=0)
    logged_data: dict[str, float | int]
    timestamp: datetime | None = None

    @field_validator("logged_data")
    @classmethod
    def validate_logged_data(cls, value: dict[str, float | int]) -> dict[str, float | int]:
        if not value:
            raise ValueError("logged_data must contain at least one metric")
        for metric_name, metric_value in value.items():
            if not metric_name.strip():
                raise ValueError("metric names must not be empty")
            if isinstance(metric_value, bool) or not isinstance(metric_value, Real):
                raise ValueError("metric values must be numeric scalars")
        return value


class RunStepBatchCreate(BaseModel):
    """Batch request for logging run metrics."""

    items: list[RunStepItemCreate] = Field(min_length=1)


class RunTerminalResponse(BaseModel):
    """Response for terminal run transitions."""

    status: str


class PlotPoint(BaseModel):
    """A single chart point."""

    step: int
    val: float
    timestamp: datetime


class RunSummaryResponse(BaseModel):
    """Frontend-friendly run summary."""

    run_number: int
    status: str
    created_at: datetime
    ended_at: datetime | None = None
    dataset: DatasetRef | None = None
    model: ModelRef | None = None
    latest_metrics: dict[str, float] = Field(default_factory=dict)
    labels: dict = Field(default_factory=dict)


class RunResponse(RunSummaryResponse):
    """Detailed run response."""

    experiment_slug: str


class ExperimentResponse(BaseModel):
    """Frontend-friendly experiment response."""

    name: str
    slug: str
    logged_data_template: list[str]
    created_at: datetime
    labels: dict = Field(default_factory=dict)
    run_count: int
    latest_run: RunSummaryResponse | None = None


class ExperimentMetricSeries(BaseModel):
    """A metric series for one run within an experiment."""

    run: RunRef
    points: list[PlotPoint] = Field(default_factory=list)


class ExperimentMetricResponse(BaseModel):
    """Comparison plot response for a metric across runs."""

    metric_name: str
    series: list[ExperimentMetricSeries] = Field(default_factory=list)


class RunMetricResponse(BaseModel):
    """Plot response for a single run metric."""

    metric_name: str
    points: list[PlotPoint] = Field(default_factory=list)


class ExperimentMetricsResponse(BaseModel):
    """Available metrics for an experiment."""

    metrics: list[str]
