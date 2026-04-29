"""
Core domain entity: Model

A model is a versioned artifact within a model repository.
Each model is linked to a specific training run and stored in MinIO.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from src.core.entities.experiment_tracking import RunRef


class Model(BaseModel):
    """A versioned model artifact within a repository."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    resource_id: uuid.UUID
    repository_id: uuid.UUID
    run_id: Optional[uuid.UUID] = None
    name: str
    version: str
    is_deleted: bool = False
    s3_uri: Optional[str] = None
    status: str = "PENDING"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelCreate(BaseModel):
    """Schema for creating a new model version."""
    name: str
    version: str
    run: Optional[RunRef] = None
    labels: dict = Field(default_factory=dict, description="Resource metadata labels")


class ModelResponse(BaseModel):
    """Response schema for model endpoints."""
    repository_slug: str
    name: str
    version: str
    run: Optional[RunRef] = None
    is_deleted: bool
    s3_uri: Optional[str] = None
    status: str
    created_at: datetime
    labels: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class ModelUploadResponse(BaseModel):
    """Response schema when requesting a pre-signed upload URL for model weights."""
    repository_slug: str
    version: str
    upload_url: str
