"""Application service: custom image artifact registry."""

import base64
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from cryptography.fernet import Fernet

from src.core.entities.artifact_registry import (
    ArtifactImage,
    ArtifactImageDeploymentCreate,
    ArtifactRegistryStatus,
    RegistryTokenCreate,
    RegistryTokenIssuedResponse,
    RegistryTokenResponse,
)
from src.core.entities.deployment import Deployment, DeploymentResponse, DeploymentTask, ImageDeployment
from src.core.entities.pagination import PaginatedResponse, SortDirection, page_items
from src.core.entities.resource import Resource
from src.core.ports.artifact_registry import FeatureConfigRepo, GiteaRegistryClient
from src.core.ports.repositories import DeploymentRepo, DeploymentTaskRepo, ResourceRepository
from src.core.slugging import slug_candidate, slugify


CUSTOM_DEPLOYMENTS_FEATURE = "custom_deployments"
CUSTOM_DEPLOYMENTS_DESCRIPTION = (
    "Allows users to manage custom Docker images in the Gitea artifact registry and deploy image tags."
)
PROXY_TOKEN_NAME = "mldlc-proxy"
PROXY_TOKEN_SCOPES = ["read:package", "read:user", "write:user"]
REGISTRY_TOKEN_SCOPES = ["read:package", "write:package"]
IMAGE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class SecretCipher:
    """Fernet encryption backed by the platform secret key."""

    def __init__(self, secret_key: str):
        digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")


class ArtifactRegistryService:
    """Coordinates per-user custom image registry workflows."""

    def __init__(
        self,
        *,
        feature_repo: FeatureConfigRepo,
        deployment_repo: DeploymentRepo,
        deployment_task_repo: DeploymentTaskRepo,
        resource_repo: ResourceRepository,
        gitea_client: GiteaRegistryClient,
        cipher: SecretCipher,
        registry_public_url: str,
    ):
        self._feature_repo = feature_repo
        self._deployment_repo = deployment_repo
        self._deployment_task_repo = deployment_task_repo
        self._resource_repo = resource_repo
        self._gitea_client = gitea_client
        self._cipher = cipher
        self._registry_host = self._host_from_url(registry_public_url)

    async def get_status(self, user_id: uuid.UUID) -> ArtifactRegistryStatus:
        await self._ensure_feature()
        config = await self._feature_repo.get_user_config(user_id, CUSTOM_DEPLOYMENTS_FEATURE)
        if not config or not config.is_active or not config.config_data.get("username"):
            return ArtifactRegistryStatus(enabled=False, registry_host=self._registry_host)
        username = str(config.config_data["username"])
        return self._status(enabled=True, username=username)

    async def enable(self, user_id: uuid.UUID, email: str) -> ArtifactRegistryStatus:
        await self._ensure_feature()
        existing = await self._feature_repo.get_user_config(user_id, CUSTOM_DEPLOYMENTS_FEATURE)
        if existing and existing.is_active and existing.config_data.get("encrypted_proxy_token"):
            if self._proxy_token_needs_refresh(existing.config_data):
                await self._refresh_proxy_token(user_id, existing)
            return self._status(enabled=True, username=str(existing.config_data["username"]))

        username = self._managed_username(user_id, email)
        bootstrap_password = secrets.token_urlsafe(32)
        await self._gitea_client.ensure_user(
            username=username,
            email=f"{username}@users.mldlc.local",
            password=bootstrap_password,
        )
        proxy_token, _metadata = await self._gitea_client.create_token_with_password(
            username,
            bootstrap_password,
            name=PROXY_TOKEN_NAME,
            scopes=PROXY_TOKEN_SCOPES,
        )
        config_data = {
            "username": username,
            "registry_host": self._registry_host,
            "encrypted_proxy_token": self._cipher.encrypt(proxy_token),
            "proxy_token_name": PROXY_TOKEN_NAME,
            "proxy_token_scopes": PROXY_TOKEN_SCOPES,
            "enabled_at": datetime.now(timezone.utc).isoformat(),
            "email": email,
        }
        await self._feature_repo.upsert_user_config(
            user_id,
            CUSTOM_DEPLOYMENTS_FEATURE,
            is_active=True,
            config_data=config_data,
        )
        return self._status(enabled=True, username=username)

    async def list_tokens(self, user_id: uuid.UUID) -> list[RegistryTokenResponse]:
        config = await self._active_config(user_id)
        return self._token_metadata_from_config(config.config_data)

    async def create_token(self, user_id: uuid.UUID, data: RegistryTokenCreate) -> RegistryTokenIssuedResponse:
        if data.name.startswith(PROXY_TOKEN_NAME):
            raise ValueError(f"Registry token names starting with '{PROXY_TOKEN_NAME}' are reserved")
        config = await self._active_config(user_id)
        username = str(config.config_data["username"])
        bootstrap_password = secrets.token_urlsafe(32)
        await self._gitea_client.reset_user_password(username, bootstrap_password)
        token, metadata = await self._gitea_client.create_token_with_password(
            username,
            bootstrap_password,
            name=data.name,
            scopes=REGISTRY_TOKEN_SCOPES,
        )
        await self._store_token_metadata(user_id, config, metadata)
        return RegistryTokenIssuedResponse(
            name=metadata.name,
            token_last_eight=metadata.token_last_eight,
            created_at=metadata.created_at,
            token=token,
            registry_host=self._registry_host,
            username=username,
            docker_login_command=self._docker_login_command(username),
        )

    async def revoke_token(self, user_id: uuid.UUID, token_name: str) -> bool:
        config = await self._active_config(user_id)
        username = str(config.config_data["username"])
        if token_name.startswith(PROXY_TOKEN_NAME):
            return False
        bootstrap_password = secrets.token_urlsafe(32)
        await self._gitea_client.reset_user_password(username, bootstrap_password)
        revoked = await self._gitea_client.revoke_token_with_password(username, bootstrap_password, token_name)
        if revoked:
            await self._remove_token_metadata(user_id, config, token_name)
        return revoked

    async def list_images(self, user_id: uuid.UUID) -> list[ArtifactImage]:
        config = await self._active_config(user_id)
        username, proxy_token = self._credentials_from_config(config.config_data)
        return await self._gitea_client.list_container_images(username, proxy_token, self._registry_host)

    async def list_images_page(
        self,
        user_id: uuid.UUID,
        *,
        search: str | None,
        sort_by: str,
        sort_dir: SortDirection,
        limit: int,
        offset: int,
    ) -> PaginatedResponse[ArtifactImage]:
        """List custom images with dashboard-oriented filtering and pagination."""
        return page_items(
            await self.list_images(user_id),
            search=search,
            search_fields=[
                lambda item: item.name,
                lambda item: " ".join(tag.tag for tag in item.tags),
                lambda item: " ".join(tag.image_ref for tag in item.tags),
            ],
            sort_by=sort_by,
            sort_dir=sort_dir,
            sort_fields={
                "name": lambda item: item.name,
                "tag_count": lambda item: len(item.tags),
                "created_at": lambda item: max((tag.created_at for tag in item.tags if tag.created_at), default=None),
            },
            limit=limit,
            offset=offset,
        )

    async def create_image_deployment(
        self,
        user_id: uuid.UUID,
        image_name: str,
        tag: str,
        data: ArtifactImageDeploymentCreate,
    ) -> DeploymentResponse:
        if not IMAGE_NAME_PATTERN.fullmatch(image_name):
            raise ValueError("Image name must be a single lowercase registry segment")

        config = await self._active_config(user_id)
        username, proxy_token = self._credentials_from_config(config.config_data)
        if not await self._gitea_client.image_tag_exists(username, proxy_token, image_name, tag):
            raise ValueError(f"Image '{image_name}:{tag}' not found")
        if await self._deployment_repo.name_exists(user_id, data.name):
            raise FileExistsError(f"Deployment '{data.name}' already exists")

        slug = await self._generate_unique_slug(user_id, data.name)
        resource = Resource(labels=data.labels)
        await self._resource_repo.create(resource)
        image_ref = f"{self._registry_host}/{username}/{image_name}:{tag}"
        deployment = Deployment(
            user_id=user_id,
            resource_id=resource.id,
            name=data.name,
            slug=slug,
            input_schema=data.input_schema,
            output_schema=data.output_schema,
            status="PENDING",
        )
        await self._deployment_repo.create_image_deployment(
            deployment,
            ImageDeployment(id=deployment.id, image_tag=image_ref),
        )
        await self._deployment_task_repo.create(DeploymentTask(deployment_id=deployment.id, type="DEPLOY"))
        return await self._build_deployment_response(deployment, image_ref)

    async def _ensure_feature(self) -> None:
        await self._feature_repo.ensure_feature(CUSTOM_DEPLOYMENTS_FEATURE, CUSTOM_DEPLOYMENTS_DESCRIPTION)

    async def _active_config(self, user_id: uuid.UUID):
        await self._ensure_feature()
        config = await self._feature_repo.get_user_config(user_id, CUSTOM_DEPLOYMENTS_FEATURE)
        if not config or not config.is_globally_enabled or not config.is_active:
            raise PermissionError("Custom deployments are not enabled")
        if not config.config_data.get("encrypted_proxy_token") or not config.config_data.get("username"):
            raise PermissionError("Custom deployments are not fully configured")
        if self._proxy_token_needs_refresh(config.config_data):
            config = await self._refresh_proxy_token(user_id, config)
        return config

    async def _refresh_proxy_token(self, user_id: uuid.UUID, config) -> object:
        username = str(config.config_data["username"])
        bootstrap_password = secrets.token_urlsafe(32)
        await self._gitea_client.reset_user_password(username, bootstrap_password)
        proxy_token_name = f"{PROXY_TOKEN_NAME}-{uuid.uuid4().hex[:8]}"
        proxy_token, _metadata = await self._gitea_client.create_token_with_password(
            username,
            bootstrap_password,
            name=proxy_token_name,
            scopes=PROXY_TOKEN_SCOPES,
        )
        config_data = {
            **config.config_data,
            "registry_host": self._registry_host,
            "encrypted_proxy_token": self._cipher.encrypt(proxy_token),
            "proxy_token_name": proxy_token_name,
            "proxy_token_scopes": PROXY_TOKEN_SCOPES,
            "proxy_token_refreshed_at": datetime.now(timezone.utc).isoformat(),
        }
        return await self._feature_repo.upsert_user_config(
            user_id,
            CUSTOM_DEPLOYMENTS_FEATURE,
            is_active=True,
            config_data=config_data,
        )

    def _proxy_token_needs_refresh(self, config_data: dict) -> bool:
        return config_data.get("proxy_token_scopes") != PROXY_TOKEN_SCOPES

    def _token_metadata_from_config(self, config_data: dict) -> list[RegistryTokenResponse]:
        raw_tokens = config_data.get("registry_tokens")
        if not isinstance(raw_tokens, dict):
            return []

        tokens: list[RegistryTokenResponse] = []
        for name, metadata in raw_tokens.items():
            if not isinstance(metadata, dict) or metadata.get("revoked_at"):
                continue
            tokens.append(
                RegistryTokenResponse(
                    name=str(metadata.get("name") or name),
                    token_last_eight=metadata.get("token_last_eight"),
                    created_at=metadata.get("created_at"),
                )
            )
        return sorted(tokens, key=lambda token: token.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    async def _store_token_metadata(self, user_id: uuid.UUID, config, token: RegistryTokenResponse) -> None:
        config_data = dict(config.config_data)
        registry_tokens = dict(config_data.get("registry_tokens") or {})
        created_at = token.created_at or datetime.now(timezone.utc)
        registry_tokens[token.name] = {
            "name": token.name,
            "token_last_eight": token.token_last_eight,
            "created_at": created_at.isoformat(),
        }
        config_data["registry_tokens"] = registry_tokens
        await self._feature_repo.upsert_user_config(
            user_id,
            CUSTOM_DEPLOYMENTS_FEATURE,
            is_active=True,
            config_data=config_data,
        )

    async def _remove_token_metadata(self, user_id: uuid.UUID, config, token_name: str) -> None:
        config_data = dict(config.config_data)
        registry_tokens = dict(config_data.get("registry_tokens") or {})
        registry_tokens.pop(token_name, None)
        config_data["registry_tokens"] = registry_tokens
        await self._feature_repo.upsert_user_config(
            user_id,
            CUSTOM_DEPLOYMENTS_FEATURE,
            is_active=True,
            config_data=config_data,
        )

    async def _build_deployment_response(self, deployment: Deployment, image_ref: str) -> DeploymentResponse:
        resource = await self._resource_repo.get_by_id(deployment.resource_id)
        return DeploymentResponse(
            name=deployment.name,
            slug=deployment.slug,
            status=deployment.status,
            endpoint_url=deployment.endpoint_url,
            input_schema=deployment.input_schema,
            output_schema=deployment.output_schema,
            created_at=deployment.created_at,
            labels=resource.labels if resource else {},
            source_type="image",
            image_ref=image_ref,
        )

    async def _generate_unique_slug(self, user_id: uuid.UUID, name: str) -> str:
        base_slug = slugify(name)
        index = 1
        while True:
            candidate = slug_candidate(base_slug, index)
            if not await self._deployment_repo.slug_exists(user_id, candidate):
                return candidate
            index += 1

    def _credentials_from_config(self, config_data: dict) -> tuple[str, str]:
        username = str(config_data["username"])
        proxy_token = self._cipher.decrypt(str(config_data["encrypted_proxy_token"]))
        return username, proxy_token

    def _status(self, *, enabled: bool, username: str) -> ArtifactRegistryStatus:
        return ArtifactRegistryStatus(
            enabled=enabled,
            registry_host=self._registry_host,
            username=username,
            namespace=f"{self._registry_host}/{username}",
            docker_login_command=self._docker_login_command(username),
        )

    def _docker_login_command(self, username: str) -> str:
        return f"docker login {self._registry_host} -u {username} --password-stdin"

    def _managed_username(self, user_id: uuid.UUID, email: str) -> str:
        local_part = email.split("@", maxsplit=1)[0].lower()
        readable_part = re.sub(r"[^a-z0-9-]+", "-", local_part).strip("-")
        readable_part = re.sub(r"-+", "-", readable_part)[:24].strip("-") or "user"
        return f"{readable_part}-{user_id.hex[:12]}"

    def _host_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc:
            return parsed.netloc
        return parsed.path.rstrip("/")
