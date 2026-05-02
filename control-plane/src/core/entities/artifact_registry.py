"""Core domain entities: Artifact Registry."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.core.entities.deployment import DeploymentCreate, DeploymentResponse


class FeatureConfig(BaseModel):
    """Per-user feature configuration."""

    name: str
    is_globally_enabled: bool
    is_active: bool
    config_data: dict[str, Any] = Field(default_factory=dict)


class ArtifactRegistryStatus(BaseModel):
    """Current user's custom image registry status."""

    enabled: bool
    registry_host: str
    username: str | None = None
    namespace: str | None = None
    docker_login_command: str | None = None


class RegistryTokenCreate(BaseModel):
    """Request to create a user-managed Docker registry token."""

    name: str


class RegistryTokenResponse(BaseModel):
    """Registry token metadata without plaintext."""

    name: str
    token_last_eight: str | None = None
    created_at: datetime | None = None


class RegistryTokenIssuedResponse(RegistryTokenResponse):
    """Registry token metadata plus one-time plaintext."""

    token: str
    registry_host: str
    username: str
    docker_login_command: str


class ArtifactImageTag(BaseModel):
    """A deployable custom image tag."""

    tag: str
    image_ref: str
    created_at: datetime | None = None


class ArtifactImage(BaseModel):
    """A custom container image and its available tags."""

    name: str
    tags: list[ArtifactImageTag] = Field(default_factory=list)


class ArtifactImageDeploymentCreate(DeploymentCreate):
    """Create a deployment from a custom image tag."""


class ArtifactImageDeploymentResponse(DeploymentResponse):
    """Image-backed deployment response."""

    source_type: str = "image"
