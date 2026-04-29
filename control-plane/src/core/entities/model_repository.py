"""
Core domain entity: Model Repository

A model repository is a logical grouping of model versions.
Different versions of the same model (e.g., "housing-predictor" v1, v2, v3)
reside within a single repository.
"""

import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional


class ModelRepository(BaseModel):
    """A logical grouping of model versions."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    resource_id: uuid.UUID
    name: str
    slug: str
    is_deleted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelRepositoryCreate(BaseModel):
    """Schema for creating a new model repository."""
    name: str
    labels: dict = Field(default_factory=dict, description="Resource metadata labels")


class ModelRepositoryResponse(BaseModel):
    """Response schema for model repository endpoints."""
    name: str
    slug: str
    is_deleted: bool
    created_at: datetime
    labels: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}
