"""Core ports for Artifact Registry integrations."""

import uuid
from abc import ABC, abstractmethod
from typing import Optional

from src.core.entities.artifact_registry import ArtifactImage, FeatureConfig, RegistryTokenResponse


class FeatureConfigRepo(ABC):
    """Port for feature flag and per-user feature configuration persistence."""

    @abstractmethod
    async def ensure_feature(self, name: str, description: str) -> None:
        ...

    @abstractmethod
    async def get_user_config(self, user_id: uuid.UUID, feature_name: str) -> Optional[FeatureConfig]:
        ...

    @abstractmethod
    async def upsert_user_config(
        self,
        user_id: uuid.UUID,
        feature_name: str,
        *,
        is_active: bool,
        config_data: dict,
    ) -> FeatureConfig:
        ...


class GiteaRegistryClient(ABC):
    """Port for the Gitea package registry API."""

    @abstractmethod
    async def ensure_user(self, username: str, email: str, password: str) -> None:
        ...

    @abstractmethod
    async def reset_user_password(self, username: str, password: str) -> None:
        ...

    @abstractmethod
    async def create_token_with_password(
        self,
        username: str,
        password: str,
        *,
        name: str,
        scopes: list[str],
    ) -> tuple[str, RegistryTokenResponse]:
        ...

    @abstractmethod
    @abstractmethod
    async def revoke_token_with_password(self, username: str, password: str, name: str) -> bool:
        ...

    @abstractmethod
    async def list_container_images(self, username: str, token: str, registry_host: str) -> list[ArtifactImage]:
        ...

    @abstractmethod
    async def image_tag_exists(self, username: str, token: str, image_name: str, tag: str) -> bool:
        ...
