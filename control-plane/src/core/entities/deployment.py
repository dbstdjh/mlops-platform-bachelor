"""Core domain entity: Deployment."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


DeploymentStatus = Literal["PENDING", "DEPLOYING", "ACTIVE", "FAILED", "DELETING", "DELETED"]
DeploymentTaskType = Literal["DEPLOY", "DELETE"]
DeploymentTaskStatus = Literal["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"]


class Deployment(BaseModel):
    """A model serving deployment tracked by the Control Plane."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    resource_id: uuid.UUID
    name: str
    slug: str
    input_schema: dict | None = None
    output_schema: dict | None = None
    endpoint_url: str | None = None
    k8s_namespace: str | None = None
    k8s_deployment_name: str | None = None
    k8s_service_name: str | None = None
    k8s_service_port: int | None = None
    status: str = "PENDING"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FileDeployment(BaseModel):
    """A deployment backed by a registered model artifact."""

    id: uuid.UUID
    model_id: uuid.UUID


class ImageDeployment(BaseModel):
    """A deployment backed by a custom container image."""

    id: uuid.UUID
    image_tag: str


class DeploymentTask(BaseModel):
    """A persisted asynchronous deployment task."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    deployment_id: uuid.UUID
    type: DeploymentTaskType
    status: DeploymentTaskStatus = "PENDING"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class DeploymentCreate(BaseModel):
    """Schema for creating a deployment for a model version."""

    name: str
    input_schema: dict | None = None
    output_schema: dict | None = None
    labels: dict = Field(default_factory=dict, description="Resource metadata labels")


class DeploymentResponse(BaseModel):
    """Response schema for deployment endpoints."""

    name: str
    slug: str
    status: str
    endpoint_url: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    created_at: datetime
    labels: dict = Field(default_factory=dict)
    source_type: Literal["file", "image"] = "file"
    image_ref: str | None = None

    model_config = {"from_attributes": True}
