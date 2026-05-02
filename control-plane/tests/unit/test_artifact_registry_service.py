import uuid

import pytest

from src.application.artifact_registry_service import ArtifactRegistryService, SecretCipher
from src.core.entities.artifact_registry import (
    ArtifactImage,
    ArtifactImageDeploymentCreate,
    ArtifactImageTag,
    FeatureConfig,
    RegistryTokenCreate,
    RegistryTokenResponse,
)
from src.core.entities.deployment import DeploymentTask


class FakeFeatureRepo:
    def __init__(self):
        self.configs = {}
        self.features = set()

    async def ensure_feature(self, name, description):
        self.features.add(name)

    async def get_user_config(self, user_id, feature_name):
        return self.configs.get((user_id, feature_name))

    async def upsert_user_config(self, user_id, feature_name, *, is_active, config_data):
        config = FeatureConfig(
            name=feature_name,
            is_globally_enabled=True,
            is_active=is_active,
            config_data=config_data,
        )
        self.configs[(user_id, feature_name)] = config
        return config


class FakeGiteaClient:
    def __init__(self):
        self.users = {}
        self.tokens = []
        self.images = [ArtifactImage(name="fraud", tags=[ArtifactImageTag(tag="latest", image_ref="host/user/fraud:latest")])]

    async def ensure_user(self, username, email, password):
        self.users[username] = {"email": email, "password": password}

    async def reset_user_password(self, username, password):
        self.users[username]["password"] = password

    async def create_token_with_password(self, username, password, *, name, scopes):
        token = f"{name}-plaintext"
        metadata = RegistryTokenResponse(name=name, token_last_eight=token[-8:])
        self.tokens.append(metadata)
        return token, metadata

    async def revoke_token_with_password(self, username, password, name):
        before = len(self.tokens)
        self.tokens = [item for item in self.tokens if item.name != name]
        return len(self.tokens) != before

    async def list_container_images(self, username, token, registry_host):
        return self.images

    async def image_tag_exists(self, username, token, image_name, tag):
        return any(image.name == image_name and any(item.tag == tag for item in image.tags) for image in self.images)


class FakeDeploymentRepo:
    def __init__(self):
        self.deployments = {}
        self.image_refs = {}

    async def create_file_deployment(self, deployment, file_deployment):
        raise AssertionError("file deployment not expected")

    async def create_image_deployment(self, deployment, image_deployment):
        self.deployments[deployment.id] = deployment
        self.image_refs[deployment.id] = image_deployment.image_tag
        return deployment

    async def get_image_ref(self, deployment_id):
        return self.image_refs.get(deployment_id)

    async def get_by_slug(self, user_id, slug):
        return None

    async def list_by_user(self, user_id):
        return []

    async def name_exists(self, user_id, name):
        return any(item.user_id == user_id and item.name == name for item in self.deployments.values())

    async def slug_exists(self, user_id, slug):
        return any(item.user_id == user_id and item.slug == slug for item in self.deployments.values())

    async def update_status(self, deployment_id, status):
        return None

    async def hard_delete(self, user_id, slug):
        return False


class FakeTaskRepo:
    def __init__(self):
        self.tasks: list[DeploymentTask] = []

    async def create(self, task):
        self.tasks.append(task)
        return task


class FakeResourceRepo:
    def __init__(self):
        self.resources = {}

    async def create(self, resource):
        self.resources[resource.id] = resource
        return resource

    async def get_by_id(self, resource_id):
        return self.resources.get(resource_id)

    async def update_labels(self, resource_id, labels):
        return None


def build_service():
    feature_repo = FakeFeatureRepo()
    deployment_repo = FakeDeploymentRepo()
    task_repo = FakeTaskRepo()
    service = ArtifactRegistryService(
        feature_repo=feature_repo,
        deployment_repo=deployment_repo,
        deployment_task_repo=task_repo,
        resource_repo=FakeResourceRepo(),
        gitea_client=FakeGiteaClient(),
        cipher=SecretCipher("test-secret"),
        registry_public_url="http://gitea.mldlc.local",
    )
    return service, feature_repo, deployment_repo, task_repo


@pytest.mark.asyncio
async def test_enable_custom_deployments_stores_encrypted_proxy_token():
    user_id = uuid.uuid4()
    service, feature_repo, _deployment_repo, _task_repo = build_service()

    status = await service.enable(user_id, "user@example.com")

    assert status.enabled is True
    config = await feature_repo.get_user_config(user_id, "custom_deployments")
    assert config.config_data["username"].startswith("user-")
    assert config.config_data["encrypted_proxy_token"] != "mldlc-proxy-plaintext"
    assert config.config_data["proxy_token_scopes"] == ["read:package", "read:user", "write:user"]


@pytest.mark.asyncio
async def test_create_registry_token_returns_plaintext_without_storing_it():
    user_id = uuid.uuid4()
    service, feature_repo, _deployment_repo, _task_repo = build_service()
    await service.enable(user_id, "user@example.com")

    issued = await service.create_token(user_id, RegistryTokenCreate(name="workstation"))

    assert issued.token == "workstation-plaintext"
    assert issued.docker_login_command.startswith("docker login gitea.mldlc.local")
    config = await feature_repo.get_user_config(user_id, "custom_deployments")
    assert "workstation-plaintext" not in str(config.config_data)


@pytest.mark.asyncio
async def test_list_registry_tokens_reads_control_plane_metadata():
    user_id = uuid.uuid4()
    service, _feature_repo, _deployment_repo, _task_repo = build_service()
    await service.enable(user_id, "user@example.com")
    await service.create_token(user_id, RegistryTokenCreate(name="workstation"))

    tokens = await service.list_tokens(user_id)

    assert [token.name for token in tokens] == ["workstation"]
    assert tokens[0].token_last_eight == "laintext"


@pytest.mark.asyncio
async def test_active_config_refreshes_old_proxy_token_scopes():
    user_id = uuid.uuid4()
    service, feature_repo, _deployment_repo, _task_repo = build_service()
    await service.enable(user_id, "user@example.com")
    config = await feature_repo.get_user_config(user_id, "custom_deployments")
    config.config_data.pop("proxy_token_scopes")
    old_encrypted_token = config.config_data["encrypted_proxy_token"]

    await service.list_tokens(user_id)

    repaired = await feature_repo.get_user_config(user_id, "custom_deployments")
    assert repaired.config_data["proxy_token_scopes"] == ["read:package", "read:user", "write:user"]
    assert repaired.config_data["encrypted_proxy_token"] != old_encrypted_token


@pytest.mark.asyncio
async def test_create_image_deployment_creates_image_record_and_task():
    user_id = uuid.uuid4()
    service, _feature_repo, deployment_repo, task_repo = build_service()
    await service.enable(user_id, "user@example.com")

    response = await service.create_image_deployment(
        user_id,
        "fraud",
        "latest",
        ArtifactImageDeploymentCreate(name="Fraud Image", labels={"env": "prod"}),
    )

    assert response.source_type == "image"
    assert response.image_ref.endswith("/fraud:latest")
    assert response.labels == {"env": "prod"}
    assert len(deployment_repo.image_refs) == 1
    assert task_repo.tasks[0].type == "DEPLOY"
