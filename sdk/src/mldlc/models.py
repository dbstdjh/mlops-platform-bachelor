from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SDKModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RunRef(SDKModel):
    experiment_slug: str
    run_number: int


class DatasetRef(SDKModel):
    dataset_slug: str
    version: int


class ModelRef(SDKModel):
    repository_slug: str
    version: str


class RunSummary(SDKModel):
    run_number: int
    status: str
    created_at: datetime
    ended_at: datetime | None = None
    dataset: DatasetRef | None = None
    model: ModelRef | None = None
    latest_metrics: dict[str, float] = Field(default_factory=dict)
    labels: dict[str, Any] = Field(default_factory=dict)


class RunInfo(RunSummary):
    experiment_slug: str


class ExperimentInfo(SDKModel):
    name: str
    slug: str
    logged_data_template: list[str]
    created_at: datetime
    labels: dict[str, Any] = Field(default_factory=dict)
    run_count: int
    latest_run: RunSummary | None = None


class DatasetVersion(SDKModel):
    name: str
    slug: str
    version: int
    status: str
    file_type: str | None = None
    created_at: datetime
    labels: dict[str, Any] = Field(default_factory=dict)


class ModelRepositoryInfo(SDKModel):
    name: str
    slug: str
    is_deleted: bool
    created_at: datetime
    labels: dict[str, Any] = Field(default_factory=dict)


class ModelVersion(SDKModel):
    repository_slug: str
    name: str
    version: str
    run: RunRef | None = None
    is_deleted: bool
    s3_uri: str | None = None
    status: str
    file_type: str
    created_at: datetime
    labels: dict[str, Any] = Field(default_factory=dict)
