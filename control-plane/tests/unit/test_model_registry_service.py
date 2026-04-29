import uuid

import pytest

from src.application.model_registry_service import MODELS_BUCKET, ModelRegistryService
from src.core.entities.experiment_tracking import Experiment, Run, RunRef
from src.core.entities.model import Model, ModelCreate
from src.core.entities.model_repository import ModelRepository, ModelRepositoryCreate
from src.core.entities.resource import Resource


class FakeResourceRepo:
    def __init__(self):
        self.resources: dict[uuid.UUID, Resource] = {}

    async def create(self, resource: Resource) -> Resource:
        self.resources[resource.id] = resource
        return resource

    async def get_by_id(self, resource_id: uuid.UUID) -> Resource | None:
        return self.resources.get(resource_id)


class FakeModelRepositoryRepo:
    def __init__(self):
        self.repositories: dict[uuid.UUID, ModelRepository] = {}
        self.deleted_keys: list[tuple[uuid.UUID, str]] = []

    async def create(self, repo: ModelRepository) -> ModelRepository:
        self.repositories[repo.id] = repo
        return repo

    async def get_by_slug(self, user_id: uuid.UUID, slug: str) -> ModelRepository | None:
        for repo in self.repositories.values():
            if repo.user_id == user_id and repo.slug == slug and not repo.is_deleted:
                return repo
        return None

    async def list_by_user(self, user_id: uuid.UUID) -> list[ModelRepository]:
        return [repo for repo in self.repositories.values() if repo.user_id == user_id and not repo.is_deleted]

    async def get_by_id(self, repository_id: uuid.UUID) -> ModelRepository | None:
        repo = self.repositories.get(repository_id)
        if repo is None or repo.is_deleted:
            return None
        return repo

    async def soft_delete(self, user_id: uuid.UUID, slug: str) -> bool:
        repo = await self.get_by_slug(user_id, slug)
        if repo is None:
            return False
        self.repositories[repo.id] = repo.model_copy(update={"is_deleted": True})
        self.deleted_keys.append((user_id, slug))
        return True

    async def slug_exists(self, user_id: uuid.UUID, slug: str) -> bool:
        return any(repo.user_id == user_id and repo.slug == slug for repo in self.repositories.values())


class FakeModelRepo:
    def __init__(self):
        self.models: dict[uuid.UUID, Model] = {}
        self.updated_s3_uris: list[tuple[uuid.UUID, str]] = []
        self.mark_ready_calls: list[uuid.UUID] = []

    async def create(self, model: Model) -> Model:
        self.models[model.id] = model
        return model

    async def get_by_version(self, repository_id: uuid.UUID, version: str) -> Model | None:
        for model in self.models.values():
            if model.repository_id == repository_id and model.version == version:
                return model
        return None

    async def list_by_repository(self, repository_id: uuid.UUID) -> list[Model]:
        return [model for model in self.models.values() if model.repository_id == repository_id]

    async def update_s3_uri(self, model_id: uuid.UUID, s3_uri: str) -> Model | None:
        model = self.models.get(model_id)
        if model is None:
            return None
        updated = model.model_copy(update={"s3_uri": s3_uri})
        self.models[model_id] = updated
        self.updated_s3_uris.append((model_id, s3_uri))
        return updated

    async def get_ready_by_version(self, repository_id: uuid.UUID, version: str) -> Model | None:
        for model in self.models.values():
            if model.repository_id == repository_id and model.version == version and model.status == "READY":
                return model
        return None

    async def mark_ready(self, model_id: uuid.UUID) -> Model | None:
        model = self.models.get(model_id)
        if model is None:
            return None
        updated = model.model_copy(update={"status": "READY"})
        self.models[model_id] = updated
        self.mark_ready_calls.append(model_id)
        return updated

    async def get_by_run_id(self, run_id: uuid.UUID) -> Model | None:
        for model in self.models.values():
            if model.run_id == run_id:
                return model
        return None


class FakeExperimentRepo:
    def __init__(self):
        self.experiments: dict[uuid.UUID, Experiment] = {}

    async def create(self, experiment: Experiment) -> Experiment:
        self.experiments[experiment.id] = experiment
        return experiment

    async def get_by_slug(self, user_id: uuid.UUID, slug: str) -> Experiment | None:
        for experiment in self.experiments.values():
            if experiment.user_id == user_id and experiment.slug == slug:
                return experiment
        return None

    async def get_by_id(self, experiment_id: uuid.UUID) -> Experiment | None:
        return self.experiments.get(experiment_id)

    async def list_by_user(self, user_id: uuid.UUID) -> list[Experiment]:
        return [experiment for experiment in self.experiments.values() if experiment.user_id == user_id]

    async def slug_exists(self, user_id: uuid.UUID, slug: str) -> bool:
        return any(experiment.user_id == user_id and experiment.slug == slug for experiment in self.experiments.values())


class FakeRunRepo:
    def __init__(self):
        self.runs: dict[uuid.UUID, Run] = {}

    async def create(self, run: Run) -> Run:
        self.runs[run.id] = run
        return run

    async def get_by_number(self, experiment_id: uuid.UUID, number: int) -> Run | None:
        for run in self.runs.values():
            if run.experiment_id == experiment_id and run.number == number:
                return run
        return None

    async def get_by_id(self, run_id: uuid.UUID) -> Run | None:
        return self.runs.get(run_id)

    async def list_by_experiment(self, experiment_id: uuid.UUID) -> list[Run]:
        return [run for run in self.runs.values() if run.experiment_id == experiment_id]

    async def get_next_number(self, experiment_id: uuid.UUID) -> int:
        numbers = [run.number for run in self.runs.values() if run.experiment_id == experiment_id]
        return (max(numbers) if numbers else 0) + 1

    async def update_status(self, run_id: uuid.UUID, status: str, ended_at=None) -> Run | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        updated = run.model_copy(update={"status": status, "ended_at": ended_at})
        self.runs[run_id] = updated
        return updated


class FakeStorage:
    def __init__(self):
        self.upload_calls: list[tuple[str, str, int]] = []
        self.download_calls: list[tuple[str, str, int]] = []
        self.object_exists_calls: list[tuple[str, str]] = []
        self.existing_objects: set[tuple[str, str]] = set()

    async def generate_upload_url(self, bucket: str, object_name: str, expires_hours: int = 1) -> str:
        self.upload_calls.append((bucket, object_name, expires_hours))
        return f"https://upload.test/{bucket}/{object_name}"

    async def generate_download_url(self, bucket: str, object_name: str, expires_hours: int = 1) -> str:
        self.download_calls.append((bucket, object_name, expires_hours))
        return f"https://download.test/{bucket}/{object_name}"

    async def object_exists(self, bucket: str, object_name: str) -> bool:
        self.object_exists_calls.append((bucket, object_name))
        return (bucket, object_name) in self.existing_objects


@pytest.fixture
def model_dependencies():
    model_repo_repo = FakeModelRepositoryRepo()
    model_repo = FakeModelRepo()
    resource_repo = FakeResourceRepo()
    experiment_repo = FakeExperimentRepo()
    run_repo = FakeRunRepo()
    storage = FakeStorage()
    service = ModelRegistryService(
        model_repo_repo=model_repo_repo,
        model_repo=model_repo,
        resource_repo=resource_repo,
        experiment_repo=experiment_repo,
        run_repo=run_repo,
        storage=storage,
    )
    return service, model_repo_repo, model_repo, resource_repo, experiment_repo, run_repo, storage


@pytest.mark.asyncio
async def test_create_repository_persists_resource_repository_and_slug(model_dependencies):
    service, model_repo_repo, _, resource_repo, _, _, _ = model_dependencies
    user_id = uuid.uuid4()

    result = await service.create_repository(
        user_id,
        ModelRepositoryCreate(name="Housing Models", labels={"problem": "regression"}),
    )

    created_repo = next(iter(model_repo_repo.repositories.values()))
    assert created_repo.user_id == user_id
    assert created_repo.name == "Housing Models"
    assert created_repo.slug == "housing-models"
    assert created_repo.resource_id in resource_repo.resources
    assert result.slug == "housing-models"
    assert result.labels == {"problem": "regression"}


@pytest.mark.asyncio
async def test_create_repository_generates_unique_slug_on_collision(model_dependencies):
    service, model_repo_repo, _, _, _, _, _ = model_dependencies
    user_id = uuid.uuid4()

    await service.create_repository(user_id, ModelRepositoryCreate(name="Vision Models"))
    result = await service.create_repository(user_id, ModelRepositoryCreate(name="Vision   Models!!!"))

    assert result.slug == "vision-models-2"
    assert any(repo.slug == "vision-models-2" for repo in model_repo_repo.repositories.values())


@pytest.mark.asyncio
async def test_get_repository_returns_none_when_missing(model_dependencies):
    service, _, _, _, _, _, _ = model_dependencies

    result = await service.get_repository(uuid.uuid4(), "missing")

    assert result is None


@pytest.mark.asyncio
async def test_get_repository_returns_response_with_resource_labels(model_dependencies):
    service, model_repo_repo, _, resource_repo, _, _, _ = model_dependencies
    resource = Resource(labels={"owner": "platform"})
    repo = ModelRepository(user_id=uuid.uuid4(), resource_id=resource.id, name="vision", slug="vision")
    await resource_repo.create(resource)
    await model_repo_repo.create(repo)

    result = await service.get_repository(repo.user_id, "vision")

    assert result is not None
    assert result.slug == "vision"
    assert result.labels == {"owner": "platform"}


@pytest.mark.asyncio
async def test_list_repositories_returns_only_user_repositories(model_dependencies):
    service, model_repo_repo, _, resource_repo, _, _, _ = model_dependencies
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    first_resource = Resource(labels={"team": "a"})
    second_resource = Resource(labels={"team": "b"})
    await resource_repo.create(first_resource)
    await resource_repo.create(second_resource)
    await model_repo_repo.create(ModelRepository(user_id=user_id, resource_id=first_resource.id, name="alpha", slug="alpha"))
    await model_repo_repo.create(ModelRepository(user_id=other_user_id, resource_id=second_resource.id, name="beta", slug="beta"))

    result = await service.list_repositories(user_id)

    assert [repo.slug for repo in result] == ["alpha"]
    assert result[0].labels == {"team": "a"}


@pytest.mark.asyncio
async def test_delete_repository_returns_delegate_result(model_dependencies):
    service, model_repo_repo, _, resource_repo, _, _, _ = model_dependencies
    resource = Resource()
    repo = ModelRepository(user_id=uuid.uuid4(), resource_id=resource.id, name="delete-me", slug="delete-me")
    await resource_repo.create(resource)
    await model_repo_repo.create(repo)

    deleted = await service.delete_repository(repo.user_id, "delete-me")
    missing = await service.delete_repository(repo.user_id, "missing")

    assert deleted is True
    assert missing is False
    assert model_repo_repo.deleted_keys == [(repo.user_id, "delete-me")]


@pytest.mark.asyncio
async def test_create_model_raises_when_repository_missing(model_dependencies):
    service, _, _, _, _, _, _ = model_dependencies

    with pytest.raises(ValueError, match="not found"):
        await service.create_model(
            uuid.uuid4(),
            "missing",
            ModelCreate(name="xgboost", version="1.0"),
        )


@pytest.mark.asyncio
async def test_create_model_persists_model_and_labels(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, _ = model_dependencies
    repository_resource = Resource()
    model_resource_labels = {"framework": "pytorch"}
    repo = ModelRepository(user_id=uuid.uuid4(), resource_id=repository_resource.id, name="cv-models", slug="cv-models")
    await resource_repo.create(repository_resource)
    await model_repo_repo.create(repo)

    result = await service.create_model(
        repo.user_id,
        "cv-models",
        ModelCreate(name="detector", version="2.1", labels=model_resource_labels),
    )

    created_model = next(iter(model_repo.models.values()))
    assert created_model.repository_id == repo.id
    assert created_model.name == "detector"
    assert created_model.version == "2.1"
    assert created_model.status == "PENDING"
    assert created_model.resource_id in resource_repo.resources
    assert result.repository_slug == "cv-models"
    assert result.labels == model_resource_labels


@pytest.mark.asyncio
async def test_create_model_resolves_public_run_reference(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, experiment_repo, run_repo, _ = model_dependencies
    user_id = uuid.uuid4()
    repository_resource = Resource()
    experiment_resource = Resource()
    run_resource = Resource()
    repo = ModelRepository(user_id=user_id, resource_id=repository_resource.id, name="cv-models", slug="cv-models")
    experiment = Experiment(
        user_id=user_id,
        resource_id=experiment_resource.id,
        name="training",
        slug="training",
        logged_data_template=["loss"],
    )
    run = Run(
        resource_id=run_resource.id,
        experiment_id=experiment.id,
        number=2,
    )
    await resource_repo.create(repository_resource)
    await resource_repo.create(experiment_resource)
    await resource_repo.create(run_resource)
    await model_repo_repo.create(repo)
    await experiment_repo.create(experiment)
    await run_repo.create(run)

    result = await service.create_model(
        user_id,
        "cv-models",
        ModelCreate(
            name="detector",
            version="2.1",
            run=RunRef(experiment_slug="training", run_number=2),
        ),
    )

    created_model = next(iter(model_repo.models.values()))
    assert created_model.run_id == run.id
    assert result.run == RunRef(experiment_slug="training", run_number=2)


@pytest.mark.asyncio
async def test_create_model_raises_when_public_run_reference_is_missing(model_dependencies):
    service, model_repo_repo, _, resource_repo, _, _, _ = model_dependencies
    user_id = uuid.uuid4()
    repository_resource = Resource()
    repo = ModelRepository(user_id=user_id, resource_id=repository_resource.id, name="cv-models", slug="cv-models")
    await resource_repo.create(repository_resource)
    await model_repo_repo.create(repo)

    with pytest.raises(ValueError, match="Experiment 'training' not found"):
        await service.create_model(
            user_id,
            "cv-models",
            ModelCreate(
                name="detector",
                version="2.1",
                run=RunRef(experiment_slug="training", run_number=2),
            ),
        )


@pytest.mark.asyncio
async def test_get_model_returns_none_when_missing(model_dependencies):
    service, _, _, _, _, _, _ = model_dependencies

    result = await service.get_model(uuid.uuid4(), "missing", "1.0")

    assert result is None


@pytest.mark.asyncio
async def test_get_model_returns_response_with_fallback_labels(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, experiment_repo, run_repo, _ = model_dependencies
    repo_resource = Resource()
    experiment_resource = Resource()
    run_resource = Resource()
    repo = ModelRepository(user_id=uuid.uuid4(), resource_id=repo_resource.id, name="recommenders", slug="recommenders")
    experiment = Experiment(
        user_id=repo.user_id,
        resource_id=experiment_resource.id,
        name="training",
        slug="training",
        logged_data_template=["loss"],
    )
    run = Run(resource_id=run_resource.id, experiment_id=experiment.id, number=7)
    model = Model(
        resource_id=uuid.uuid4(),
        repository_id=repo.id,
        run_id=run.id,
        name="recommender",
        version="1.0",
    )
    await resource_repo.create(repo_resource)
    await resource_repo.create(experiment_resource)
    await resource_repo.create(run_resource)
    await model_repo_repo.create(repo)
    await experiment_repo.create(experiment)
    await run_repo.create(run)
    await model_repo.create(model)

    result = await service.get_model(repo.user_id, "recommenders", "1.0")

    assert result is not None
    assert result.repository_slug == "recommenders"
    assert result.labels == {}
    assert result.run == RunRef(experiment_slug="training", run_number=7)


@pytest.mark.asyncio
async def test_list_models_returns_repository_models_with_labels(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, _ = model_dependencies
    owner_id = uuid.uuid4()
    repo_resource = Resource()
    model_resource = Resource(labels={"family": "nlp"})
    other_resource = Resource(labels={"family": "vision"})
    repo = ModelRepository(user_id=owner_id, resource_id=repo_resource.id, name="embedders", slug="embedders")
    other_repo = ModelRepository(user_id=owner_id, resource_id=uuid.uuid4(), name="vision", slug="vision")
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    await resource_repo.create(other_resource)
    await model_repo_repo.create(repo)
    await model_repo_repo.create(other_repo)
    await model_repo.create(Model(resource_id=model_resource.id, repository_id=repo.id, name="encoder", version="1"))
    await model_repo.create(Model(resource_id=other_resource.id, repository_id=other_repo.id, name="detector", version="1"))

    result = await service.list_models(owner_id, "embedders")

    assert [model.name for model in result] == ["encoder"]
    assert result[0].labels == {"family": "nlp"}


@pytest.mark.asyncio
async def test_list_models_raises_when_repository_missing(model_dependencies):
    service, _, _, _, _, _, _ = model_dependencies

    with pytest.raises(ValueError, match="not found"):
        await service.list_models(uuid.uuid4(), "missing")


@pytest.mark.asyncio
async def test_get_upload_url_returns_none_when_model_missing(model_dependencies):
    service, model_repo_repo, _, resource_repo, _, _, _ = model_dependencies
    repo_resource = Resource()
    repo = ModelRepository(user_id=uuid.uuid4(), resource_id=repo_resource.id, name="fraud", slug="fraud")
    await resource_repo.create(repo_resource)
    await model_repo_repo.create(repo)

    result = await service.get_upload_url(repo.user_id, "fraud", "1.0")

    assert result is None


@pytest.mark.asyncio
async def test_get_upload_url_updates_s3_uri_and_returns_signed_url(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, storage = model_dependencies
    owner_id = uuid.uuid4()
    repo_resource = Resource()
    model_resource = Resource()
    repo = ModelRepository(user_id=owner_id, resource_id=repo_resource.id, name="fraud", slug="fraud")
    model = Model(
        resource_id=model_resource.id,
        repository_id=repo.id,
        name="fraud-detector",
        version="3.4",
    )
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    await model_repo_repo.create(repo)
    await model_repo.create(model)

    result = await service.get_upload_url(owner_id, "fraud", "3.4")

    expected_object_name = f"{owner_id}/fraud/fraud-detector/v3.4"
    assert result is not None
    assert result.repository_slug == "fraud"
    assert result.version == "3.4"
    assert result.upload_url == f"https://upload.test/{MODELS_BUCKET}/{expected_object_name}"
    assert model_repo.models[model.id].s3_uri == f"s3://{MODELS_BUCKET}/{expected_object_name}"
    assert storage.upload_calls == [(MODELS_BUCKET, expected_object_name, 1)]
    assert model_repo.models[model.id].status == "PENDING"


@pytest.mark.asyncio
async def test_confirm_upload_returns_false_when_repository_missing(model_dependencies):
    service, _, _, _, _, _, _ = model_dependencies

    result = await service.confirm_upload(uuid.uuid4(), "missing", "1.0")

    assert result is False


@pytest.mark.asyncio
async def test_confirm_upload_raises_when_upload_not_initiated(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, _ = model_dependencies
    owner_id = uuid.uuid4()
    repo_resource = Resource()
    model_resource = Resource()
    repo = ModelRepository(user_id=owner_id, resource_id=repo_resource.id, name="fraud", slug="fraud")
    model = Model(
        resource_id=model_resource.id,
        repository_id=repo.id,
        name="fraud-detector",
        version="3.4",
    )
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    await model_repo_repo.create(repo)
    await model_repo.create(model)

    with pytest.raises(ValueError, match="not been initiated"):
        await service.confirm_upload(owner_id, "fraud", "3.4")


@pytest.mark.asyncio
async def test_confirm_upload_raises_when_object_missing_in_storage(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, storage = model_dependencies
    owner_id = uuid.uuid4()
    repo_resource = Resource()
    model_resource = Resource()
    repo = ModelRepository(user_id=owner_id, resource_id=repo_resource.id, name="fraud", slug="fraud")
    model = Model(
        resource_id=model_resource.id,
        repository_id=repo.id,
        name="fraud-detector",
        version="3.4",
        s3_uri=f"s3://{MODELS_BUCKET}/{owner_id}/fraud/fraud-detector/v3.4",
    )
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    await model_repo_repo.create(repo)
    await model_repo.create(model)

    with pytest.raises(ValueError, match="not found in storage"):
        await service.confirm_upload(owner_id, "fraud", "3.4")

    assert storage.object_exists_calls == [(MODELS_BUCKET, f"{owner_id}/fraud/fraud-detector/v3.4")]


@pytest.mark.asyncio
async def test_confirm_upload_marks_model_ready_when_object_exists(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, storage = model_dependencies
    owner_id = uuid.uuid4()
    repo_resource = Resource()
    model_resource = Resource()
    repo = ModelRepository(user_id=owner_id, resource_id=repo_resource.id, name="fraud", slug="fraud")
    object_name = f"{owner_id}/fraud/fraud-detector/v3.4"
    model = Model(
        resource_id=model_resource.id,
        repository_id=repo.id,
        name="fraud-detector",
        version="3.4",
        s3_uri=f"s3://{MODELS_BUCKET}/{object_name}",
    )
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    await model_repo_repo.create(repo)
    await model_repo.create(model)
    storage.existing_objects.add((MODELS_BUCKET, object_name))

    result = await service.confirm_upload(owner_id, "fraud", "3.4")

    assert result is True
    assert model_repo.models[model.id].status == "READY"
    assert model_repo.mark_ready_calls == [model.id]
    assert model_repo.updated_s3_uris == [(model.id, f"s3://{MODELS_BUCKET}/{object_name}")]


@pytest.mark.asyncio
async def test_confirm_upload_from_object_key_returns_false_for_invalid_key_shape(model_dependencies):
    service, _, _, _, _, _, _ = model_dependencies

    result = await service.confirm_upload_from_object_key("too-short")

    assert result is False


@pytest.mark.asyncio
async def test_confirm_upload_from_object_key_returns_false_for_invalid_user_id(model_dependencies):
    service, _, _, _, _, _, _ = model_dependencies

    result = await service.confirm_upload_from_object_key("not-a-uuid/repo/model/v1.0")

    assert result is False


@pytest.mark.asyncio
async def test_confirm_upload_from_object_key_returns_false_when_model_name_mismatches(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, _ = model_dependencies
    owner_id = uuid.uuid4()
    repo_resource = Resource()
    model_resource = Resource()
    repo = ModelRepository(user_id=owner_id, resource_id=repo_resource.id, name="fraud", slug="fraud")
    model = Model(
        resource_id=model_resource.id,
        repository_id=repo.id,
        name="fraud-detector",
        version="3.4",
    )
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    await model_repo_repo.create(repo)
    await model_repo.create(model)

    result = await service.confirm_upload_from_object_key(f"{owner_id}/fraud/other-model/v3.4")

    assert result is False


@pytest.mark.asyncio
async def test_confirm_upload_from_object_key_marks_model_ready(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, _ = model_dependencies
    owner_id = uuid.uuid4()
    repo_resource = Resource()
    model_resource = Resource()
    repo = ModelRepository(user_id=owner_id, resource_id=repo_resource.id, name="fraud", slug="fraud")
    model = Model(
        resource_id=model_resource.id,
        repository_id=repo.id,
        name="fraud-detector",
        version="3.4",
    )
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    await model_repo_repo.create(repo)
    await model_repo.create(model)

    result = await service.confirm_upload_from_object_key(f"{owner_id}/fraud/fraud-detector/v3.4")

    assert result is True
    assert model_repo.models[model.id].status == "READY"
    assert model_repo.updated_s3_uris == [(model.id, f"s3://{MODELS_BUCKET}/{owner_id}/fraud/fraud-detector/v3.4")]


@pytest.mark.asyncio
async def test_get_download_url_returns_none_when_ready_model_missing(model_dependencies):
    service, _, _, _, _, _, _ = model_dependencies

    result = await service.get_download_url(uuid.uuid4(), "missing", "1.0")

    assert result is None


@pytest.mark.asyncio
async def test_get_download_url_returns_signed_url_for_ready_model(model_dependencies):
    service, model_repo_repo, model_repo, resource_repo, _, _, storage = model_dependencies
    owner_id = uuid.uuid4()
    repo_resource = Resource()
    model_resource = Resource()
    repo = ModelRepository(user_id=owner_id, resource_id=repo_resource.id, name="fraud", slug="fraud")
    object_name = f"{owner_id}/fraud/fraud-detector/v3.4"
    model = Model(
        resource_id=model_resource.id,
        repository_id=repo.id,
        name="fraud-detector",
        version="3.4",
        s3_uri=f"s3://{MODELS_BUCKET}/{object_name}",
        status="READY",
    )
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    await model_repo_repo.create(repo)
    await model_repo.create(model)

    result = await service.get_download_url(owner_id, "fraud", "3.4")

    assert result == f"https://download.test/{MODELS_BUCKET}/{object_name}"
    assert storage.download_calls == [(MODELS_BUCKET, object_name, 1)]
