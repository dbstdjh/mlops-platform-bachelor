"""
Core domain entities and API contracts for saved run dashboards.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PlotType = Literal["line", "stat"]
DashboardKind = Literal["RUN_PLOT"]


class Dashboard(BaseModel):
    """Persisted dashboard metadata shared across observability resources."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    kind: DashboardKind = "RUN_PLOT"
    grafana_uid: str | None = None
    is_system_locked: bool = False
    config_data: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunDashboard(BaseModel):
    """Join entity that links a dashboard to a run."""

    id: uuid.UUID
    run_id: uuid.UUID
    display_order: int = Field(ge=0)


class RunDashboardRecord(BaseModel):
    """Application-facing saved run plot."""

    id: uuid.UUID
    run_id: uuid.UUID
    title: str
    plot_type: PlotType
    metrics: list[str]
    display_order: int = Field(ge=0)
    grafana_uid: str | None = None
    created_at: datetime


class RunDashboardCreate(BaseModel):
    """Request payload for creating a saved run plot."""

    title: str = Field(min_length=1, max_length=120)
    plot_type: PlotType
    metrics: list[str]

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be empty")
        return normalized

    @field_validator("metrics")
    @classmethod
    def normalize_metrics(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            metric = item.strip()
            if not metric or metric in seen:
                continue
            seen.add(metric)
            normalized.append(metric)
        if not normalized:
            raise ValueError("metrics must contain at least one metric")
        return normalized

    @model_validator(mode="after")
    def validate_plot_rules(self) -> "RunDashboardCreate":
        if self.plot_type == "stat" and len(self.metrics) != 1:
            raise ValueError("stat plots must contain exactly one metric")
        return self


class RunDashboardUpdate(BaseModel):
    """Patch payload for updating a saved run plot."""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    plot_type: PlotType | None = None
    metrics: list[str] | None = None
    display_order: int | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be empty")
        return normalized

    @field_validator("metrics")
    @classmethod
    def normalize_metrics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            metric = item.strip()
            if not metric or metric in seen:
                continue
            seen.add(metric)
            normalized.append(metric)
        if not normalized:
            raise ValueError("metrics must contain at least one metric")
        return normalized

    @model_validator(mode="after")
    def validate_non_empty_patch(self) -> "RunDashboardUpdate":
        if self.title is None and self.plot_type is None and self.metrics is None and self.display_order is None:
            raise ValueError("at least one field must be provided")
        return self


class RunDashboardResponse(BaseModel):
    """Frontend-friendly saved run plot response."""

    id: uuid.UUID
    title: str
    plot_type: PlotType
    metrics: list[str]
    display_order: int
    iframe_url: str
    created_at: datetime
