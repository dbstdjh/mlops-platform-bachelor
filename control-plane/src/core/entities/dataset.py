"""
Core domain entity: Dataset

A versioned dataset within the Feature Registry.
Datasets follow a strict lifecycle: PENDING → READY.
"""

import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional


class Dataset(BaseModel):
    """A versioned dataset in the Feature Registry."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    resource_id: uuid.UUID
    name: str
    slug: str
    s3_uri: Optional[str] = None
    status: str = "PENDING"
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    file_type: Optional[str] = None


class DatasetCreate(BaseModel):
    """Schema for initiating a dataset upload."""
    name: str
    file_type: str = "parquet"
    labels: dict = Field(default_factory=dict, description="Resource metadata labels")


class DatasetResponse(BaseModel):
    """Response schema for dataset endpoints."""
    name: str
    slug: str
    version: int
    status: str
    file_type: Optional[str] = None
    created_at: datetime
    labels: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class DatasetUploadResponse(BaseModel):
    """Response when initiating a dataset upload — contains the pre-signed URL."""
    dataset_slug: str
    upload_url: str
    version: int
