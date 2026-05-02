import uuid

import pytest

from src.application.deployment_service import DeploymentService
from src.core.entities.dashboard import DeploymentDashboardCreate, DeploymentDashboardRecord
from src.core.entities.deployment import Deployment, DeploymentCreate, DeploymentTask
from src.core.entities.model import Model
from src.core.entities.model_repository import ModelRepository
from src.core.entities.resource import Resource


class FakeResourceRepo:
    def __init__(self):
        self.resources = {}

    async def create(self, resource):
        self.resources[resource.id] = resource
        return resource

    async def get_by_id(self, resource_id):
        return self.resources.get(resource_id)

    async def update_labels(self, resource_id, labels):
        resource = self.resources[resource_id].model_copy(update={"labels": labels})
        self.resources[resource_id] = resource
        return resource


class FakeModelRepositoryRepo:
    def __init__(self, repo):
        self.repo = repo

    async def get_by_slug(self, user_id, slug):
        if self.repo.user_id == user_id and self.repo.slug == slug:
            return self.repo
        return None


class FakeModelRepo:
    def __init__(self, model):
        self.model = model

    async def get_ready_by_version(self, repository_id, version):
        if (
            self.model.repository_id == repository_id
            and self.model.version == version
            and self.model.status == "READY"
        ):
            return self.model
        return None


class FakeDeploymentRepo:
    def __init__(self):
        self.deployments = {}

    async def create_file_deployment(self, deployment, file_deployment):
        self.deployments[deployment.id] = deployment
        self.file_deployment = file_deployment
        return deployment

    async def create_image_deployment(self, deployment, image_deployment):
        self.deployments[deployment.id] = deployment
        self.image_deployment = image_deployment
        return deployment

    async def get_image_ref(self, deployment_id):
        return getattr(self, "image_deployment", None).image_tag if getattr(self, "image_deployment", None) else None

    async def get_by_slug(self, user_id, slug):
        for deployment in self.deployments.values():
            if deployment.user_id == user_id and deployment.slug == slug:
                return deployment
        return None

    async def list_by_user(self, user_id):
        return [deployment for deployment in self.deployments.values() if deployment.user_id == user_id]

    async def name_exists(self, user_id, name):
        return any(deployment.user_id == user_id and deployment.name == name for deployment in self.deployments.values())

    async def slug_exists(self, user_id, slug):
        return any(deployment.user_id == user_id and deployment.slug == slug for deployment in self.deployments.values())

    async def update_status(self, deployment_id, status):
        deployment = self.deployments[deployment_id].model_copy(update={"status": status})
        self.deployments[deployment_id] = deployment
        return deployment

    async def hard_delete(self, user_id, slug):
        for deployment_id, deployment in list(self.deployments.items()):
            if deployment.user_id == user_id and deployment.slug == slug:
                del self.deployments[deployment_id]
                return True
        return False


class FakeTaskRepo:
    def __init__(self):
        self.tasks: list[DeploymentTask] = []

    async def create(self, task):
        self.tasks.append(task)
        return task


class FakeDashboardRepo:
    def __init__(self):
        self.items = {}

    async def create_deployment_dashboard(self, dashboard, *, deployment_id):
        record = DeploymentDashboardRecord(
            id=dashboard.id,
            deployment_id=deployment_id,
            title=dashboard.name,
            plot_type=dashboard.config_data["plot_type"],
            source=dashboard.config_data["source"],
            field_path=dashboard.config_data["field_path"],
            is_system_locked=dashboard.is_system_locked,
            grafana_uid=dashboard.grafana_uid,
            created_at=dashboard.created_at,
        )
        self.items[dashboard.id] = record
        return record

    async def list_by_deployment(self, deployment_id):
        return [item for item in self.items.values() if item.deployment_id == deployment_id]

    async def get_by_id_for_deployment(self, deployment_id, dashboard_id):
        item = self.items.get(dashboard_id)
        if not item or item.deployment_id != deployment_id:
            return None
        return item

    async def delete_deployment_dashboard(self, deployment_id, dashboard_id):
        item = self.items.get(dashboard_id)
        if not item or item.deployment_id != deployment_id:
            return False
        del self.items[dashboard_id]
        return True


class FakeGrafanaClient:
    def __init__(self):
        self.upserts = []
        self.deleted = []

    async def upsert_deployment_plot(self, **kwargs):
        self.upserts.append(kwargs)
        return kwargs["grafana_uid"] or f"deployment-grafana-{len(self.upserts)}"

    async def upsert_run_plot(self, **kwargs):
        raise AssertionError("run plot not expected")

    async def delete_dashboard(self, grafana_uid):
        self.deleted.append(grafana_uid)

    def build_solo_iframe_url(self, grafana_uid):
        return f"http://grafana.local/d-solo/{grafana_uid}/deployment-plot?panelId=1"


@pytest.mark.asyncio
async def test_create_model_deployment_creates_record_and_task():
    user_id = uuid.uuid4()
    repo = ModelRepository(user_id=user_id, resource_id=uuid.uuid4(), name="fraud", slug="fraud")
    model = Model(
        resource_id=uuid.uuid4(),
        repository_id=repo.id,
        name="classifier",
        version="1.0",
        status="READY",
        file_type="pickle",
        s3_uri="s3://models/user/fraud/classifier/model.pkl",
    )
    deployment_repo = FakeDeploymentRepo()
    task_repo = FakeTaskRepo()
    service = DeploymentService(
        deployment_repo=deployment_repo,
        deployment_task_repo=task_repo,
        model_repo_repo=FakeModelRepositoryRepo(repo),
        model_repo=FakeModelRepo(model),
        resource_repo=FakeResourceRepo(),
    )

    response = await service.create_model_deployment(
        user_id,
        "fraud",
        "1.0",
        DeploymentCreate(name="Fraud Prod", labels={"env": "prod"}),
    )

    assert response.slug == "fraud-prod"
    assert response.status == "PENDING"
    assert response.labels == {"env": "prod"}
    assert len(task_repo.tasks) == 1
    assert task_repo.tasks[0].type == "DEPLOY"
    assert deployment_repo.file_deployment.model_id == model.id


@pytest.mark.asyncio
async def test_create_model_deployment_rejects_non_pickle_model():
    user_id = uuid.uuid4()
    repo = ModelRepository(user_id=user_id, resource_id=uuid.uuid4(), name="fraud", slug="fraud")
    model = Model(
        resource_id=uuid.uuid4(),
        repository_id=repo.id,
        name="classifier",
        version="1.0",
        status="READY",
        file_type="undefined",
    )
    service = DeploymentService(
        deployment_repo=FakeDeploymentRepo(),
        deployment_task_repo=FakeTaskRepo(),
        model_repo_repo=FakeModelRepositoryRepo(repo),
        model_repo=FakeModelRepo(model),
        resource_repo=FakeResourceRepo(),
    )

    with pytest.raises(ValueError, match="Only pickle"):
        await service.create_model_deployment(user_id, "fraud", "1.0", DeploymentCreate(name="prod"))


@pytest.mark.asyncio
async def test_deployment_dashboards_create_default_panels_and_extract_plot_fields():
    user_id = uuid.uuid4()
    deployment_repo = FakeDeploymentRepo()
    dashboard_repo = FakeDashboardRepo()
    grafana_client = FakeGrafanaClient()
    resource_repo = FakeResourceRepo()
    resource = Resource(labels={"env": "prod"})
    await resource_repo.create(resource)
    deployment = Deployment(
        user_id=user_id,
        resource_id=resource.id,
        name="Fraud Prod",
        slug="fraud-prod",
        status="ACTIVE",
        input_schema={
            "type": "object",
            "$defs": {
                "FeatureVector": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {"type": "number"},
                }
            },
            "properties": {
                "amount": {"type": "number"},
                "features": {"type": "array", "items": {"type": "number"}},
                "instances": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/FeatureVector"},
                },
                "ignored": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "predictions": {"type": "array", "items": {"type": "string"}},
                "accepted": {"type": ["boolean", "null"]},
            },
        },
    )
    deployment_repo.deployments[deployment.id] = deployment
    service = DeploymentService(
        deployment_repo=deployment_repo,
        deployment_task_repo=FakeTaskRepo(),
        model_repo_repo=FakeModelRepositoryRepo(ModelRepository(user_id=user_id, resource_id=uuid.uuid4(), name="x", slug="x")),
        model_repo=FakeModelRepo(Model(resource_id=uuid.uuid4(), repository_id=uuid.uuid4(), name="x", version="1.0")),
        resource_repo=resource_repo,
        dashboard_repo=dashboard_repo,
        grafana_client=grafana_client,
    )

    dashboards = await service.list_deployment_dashboards(user_id, "fraud-prod")
    fields = await service.list_plot_fields(user_id, "fraud-prod")

    assert [dashboard.plot_type for dashboard in dashboards] == ["latency", "status_code"]
    assert all(dashboard.is_system_locked for dashboard in dashboards)
    assert [call["plot_type"] for call in grafana_client.upserts] == ["latency", "status_code"]
    assert [(field.source, field.path, field.value_type) for field in fields] == [
        ("input", "amount", "number"),
        ("input", "features[*]", "number_array"),
        ("input", "ignored", "category"),
        ("input", "instances[*][*]", "number_matrix"),
        ("input", "instances[*][0]", "number_matrix_index"),
        ("input", "instances[*][1]", "number_matrix_index"),
        ("input", "instances[*][2]", "number_matrix_index"),
        ("output", "accepted", "boolean"),
        ("output", "predictions[*]", "category_array"),
        ("output", "score", "number"),
    ]
    assert fields[0].plot_types == ["time_series", "distribution"]
    assert next(field for field in fields if field.path == "instances[*][*]").plot_types == ["distribution"]
    assert next(field for field in fields if field.path == "predictions[*]").plot_types == ["distribution", "category_time_series"]


@pytest.mark.asyncio
async def test_create_and_delete_custom_deployment_dashboard():
    user_id = uuid.uuid4()
    deployment_repo = FakeDeploymentRepo()
    dashboard_repo = FakeDashboardRepo()
    grafana_client = FakeGrafanaClient()
    resource_repo = FakeResourceRepo()
    resource = Resource()
    await resource_repo.create(resource)
    deployment = Deployment(
        user_id=user_id,
        resource_id=resource.id,
        name="Fraud Prod",
        slug="fraud-prod",
        input_schema={"type": "object", "properties": {"amount": {"type": "number"}}},
    )
    deployment_repo.deployments[deployment.id] = deployment
    service = DeploymentService(
        deployment_repo=deployment_repo,
        deployment_task_repo=FakeTaskRepo(),
        model_repo_repo=FakeModelRepositoryRepo(ModelRepository(user_id=user_id, resource_id=uuid.uuid4(), name="x", slug="x")),
        model_repo=FakeModelRepo(Model(resource_id=uuid.uuid4(), repository_id=uuid.uuid4(), name="x", version="1.0")),
        resource_repo=resource_repo,
        dashboard_repo=dashboard_repo,
        grafana_client=grafana_client,
    )

    created = await service.create_deployment_dashboard(
        user_id,
        "fraud-prod",
        DeploymentDashboardCreate(
            title="Amount distribution",
            plot_type="distribution",
            source="input",
            field_path="amount",
        ),
    )
    await service.delete_deployment_dashboard(user_id, "fraud-prod", created.id)

    assert created.is_system_locked is False
    assert created.field_path == "amount"
    assert grafana_client.deleted == ["deployment-grafana-1"]


@pytest.mark.asyncio
async def test_create_deployment_dashboard_rejects_invalid_plot_type_for_field():
    user_id = uuid.uuid4()
    deployment_repo = FakeDeploymentRepo()
    dashboard_repo = FakeDashboardRepo()
    grafana_client = FakeGrafanaClient()
    resource_repo = FakeResourceRepo()
    resource = Resource()
    await resource_repo.create(resource)
    deployment = Deployment(
        user_id=user_id,
        resource_id=resource.id,
        name="Fraud Prod",
        slug="fraud-prod",
        output_schema={"type": "object", "properties": {"predictions": {"type": "array", "items": {"type": "string"}}}},
    )
    deployment_repo.deployments[deployment.id] = deployment
    service = DeploymentService(
        deployment_repo=deployment_repo,
        deployment_task_repo=FakeTaskRepo(),
        model_repo_repo=FakeModelRepositoryRepo(ModelRepository(user_id=user_id, resource_id=uuid.uuid4(), name="x", slug="x")),
        model_repo=FakeModelRepo(Model(resource_id=uuid.uuid4(), repository_id=uuid.uuid4(), name="x", version="1.0")),
        resource_repo=resource_repo,
        dashboard_repo=dashboard_repo,
        grafana_client=grafana_client,
    )

    with pytest.raises(ValueError, match="Plot type 'time_series' is not available"):
        await service.create_deployment_dashboard(
            user_id,
            "fraud-prod",
            DeploymentDashboardCreate(
                title="Prediction timeline",
                plot_type="time_series",
                source="output",
                field_path="predictions[*]",
            ),
        )


@pytest.mark.asyncio
async def test_purge_deployment_removes_record():
    user_id = uuid.uuid4()
    deployment_repo = FakeDeploymentRepo()
    deployment = Deployment(user_id=user_id, resource_id=uuid.uuid4(), name="Fraud Prod", slug="fraud-prod")
    deployment_repo.deployments[deployment.id] = deployment
    service = DeploymentService(
        deployment_repo=deployment_repo,
        deployment_task_repo=FakeTaskRepo(),
        model_repo_repo=FakeModelRepositoryRepo(ModelRepository(user_id=user_id, resource_id=uuid.uuid4(), name="x", slug="x")),
        model_repo=FakeModelRepo(Model(resource_id=uuid.uuid4(), repository_id=uuid.uuid4(), name="x", version="1.0")),
        resource_repo=FakeResourceRepo(),
    )

    assert await service.purge_deployment(user_id, "fraud-prod") is True
    assert await deployment_repo.get_by_slug(user_id, "fraud-prod") is None
