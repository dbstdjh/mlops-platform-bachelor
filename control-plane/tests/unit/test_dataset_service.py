import uuid

import pytest

from src.application.dataset_service import DATASETS_BUCKET, DatasetService
from src.core.entities.dataset import Dataset, DatasetCreate
from src.core.entities.resource import Resource


class FakeResourceRepo:
    def __init__(self):
        self.resources: dict[uuid.UUID, Resource] = {}

    async def create(self, resource: Resource) -> Resource:
        self.resources[resource.id] = resource
        return resource

    async def get_by_id(self, resource_id: uuid.UUID) -> Resource | None:
        return self.resources.get(resource_id)


class FakeDatasetRepo:
    def __init__(self):
        self.datasets: dict[uuid.UUID, Dataset] = {}
        self.mark_ready_calls: list[tuple[str, uuid.UUID, int, str]] = []

    async def create(self, dataset: Dataset) -> Dataset:
        self.datasets[dataset.id] = dataset
        return dataset

    async def get_latest_by_name(self, name: str, user_id: uuid.UUID) -> Dataset | None:
        matches = [
            dataset
            for dataset in self.datasets.values()
            if dataset.user_id == user_id and dataset.name == name
        ]
        if not matches:
            return None
        return max(matches, key=lambda dataset: dataset.version)

    async def get_by_slug_and_version(self, slug: str, user_id: uuid.UUID, version: int) -> Dataset | None:
        for dataset in self.datasets.values():
            if dataset.user_id == user_id and dataset.slug == slug and dataset.version == version:
                return dataset
        return None

    async def get_latest_ready(self, slug: str, user_id: uuid.UUID) -> Dataset | None:
        ready_matches = [
            dataset
            for dataset in self.datasets.values()
            if dataset.user_id == user_id and dataset.slug == slug and dataset.status == "READY"
        ]
        if not ready_matches:
            return None
        return max(ready_matches, key=lambda dataset: dataset.version)

    async def get_ready_by_slug_and_version(self, slug: str, user_id: uuid.UUID, version: int) -> Dataset | None:
        dataset = await self.get_by_slug_and_version(slug, user_id, version)
        if dataset and dataset.status == "READY":
            return dataset
        return None

    async def list_by_user(self, user_id: uuid.UUID) -> list[Dataset]:
        return [dataset for dataset in self.datasets.values() if dataset.user_id == user_id]

    async def mark_ready(self, slug: str, user_id: uuid.UUID, version: int, s3_uri: str) -> Dataset | None:
        dataset = await self.get_by_slug_and_version(slug, user_id, version)
        if dataset is None:
            return None
        ready_dataset = dataset.model_copy(update={"status": "READY", "s3_uri": s3_uri})
        self.datasets[dataset.id] = ready_dataset
        self.mark_ready_calls.append((slug, user_id, version, s3_uri))
        return ready_dataset

    async def get_next_version(self, slug: str, user_id: uuid.UUID) -> int:
        versions = [
            dataset.version
            for dataset in self.datasets.values()
            if dataset.user_id == user_id and dataset.slug == slug
        ]
        return (max(versions) if versions else 0) + 1

    async def slug_exists(self, slug: str, user_id: uuid.UUID) -> bool:
        return any(dataset.user_id == user_id and dataset.slug == slug for dataset in self.datasets.values())


class FakeStorage:
    def __init__(self):
        self.upload_calls: list[tuple[str, str, int]] = []
        self.download_calls: list[tuple[str, str, int]] = []

    async def generate_upload_url(self, bucket: str, object_name: str, expires_hours: int = 1) -> str:
        self.upload_calls.append((bucket, object_name, expires_hours))
        return f"https://upload.test/{bucket}/{object_name}"

    async def generate_download_url(self, bucket: str, object_name: str, expires_hours: int = 1) -> str:
        self.download_calls.append((bucket, object_name, expires_hours))
        return f"https://download.test/{bucket}/{object_name}"


@pytest.fixture
def dataset_dependencies():
    dataset_repo = FakeDatasetRepo()
    resource_repo = FakeResourceRepo()
    storage = FakeStorage()
    service = DatasetService(dataset_repo=dataset_repo, resource_repo=resource_repo, storage=storage)
    return service, dataset_repo, resource_repo, storage


@pytest.mark.asyncio
async def test_initiate_upload_creates_pending_dataset_and_signed_url(dataset_dependencies):
    service, dataset_repo, resource_repo, storage = dataset_dependencies
    user_id = uuid.uuid4()

    response = await service.initiate_upload(
        user_id,
        DatasetCreate(name="housing-data", file_type="csv", labels={"source": "sdk"}),
    )

    created_dataset = next(iter(dataset_repo.datasets.values()))
    assert created_dataset.user_id == user_id
    assert created_dataset.name == "housing-data"
    assert created_dataset.slug == "housing-data"
    assert created_dataset.version == 1
    assert created_dataset.status == "PENDING"
    assert created_dataset.s3_uri == f"s3://{DATASETS_BUCKET}/{user_id}/housing-data/v1.csv"
    assert response.dataset_slug == "housing-data"
    assert response.upload_url == f"https://upload.test/{DATASETS_BUCKET}/{user_id}/housing-data/v1.csv"
    assert response.version == 1
    assert storage.upload_calls == [(DATASETS_BUCKET, f"{user_id}/housing-data/v1.csv", 1)]
    assert created_dataset.resource_id in resource_repo.resources


@pytest.mark.asyncio
async def test_initiate_upload_reuses_existing_slug_for_same_name(dataset_dependencies):
    service, dataset_repo, _, _ = dataset_dependencies
    user_id = uuid.uuid4()

    first = await service.initiate_upload(user_id, DatasetCreate(name="churn", file_type="parquet"))
    second = await service.initiate_upload(user_id, DatasetCreate(name="churn", file_type="parquet"))

    assert first.dataset_slug == "churn"
    assert second.dataset_slug == "churn"
    assert second.version == 2


@pytest.mark.asyncio
async def test_initiate_upload_generates_unique_slug_for_colliding_names(dataset_dependencies):
    service, dataset_repo, _, _ = dataset_dependencies
    user_id = uuid.uuid4()

    await service.initiate_upload(user_id, DatasetCreate(name="Sales Data", file_type="csv"))
    response = await service.initiate_upload(user_id, DatasetCreate(name="Sales   Data!!!", file_type="csv"))

    assert response.dataset_slug == "sales-data-2"
    latest = max(dataset_repo.datasets.values(), key=lambda dataset: dataset.created_at)
    assert latest.slug == "sales-data-2"


@pytest.mark.asyncio
async def test_confirm_upload_returns_false_for_short_object_key(dataset_dependencies):
    service, _, _, _ = dataset_dependencies

    result = await service.confirm_upload("too-short")

    assert result is False


@pytest.mark.asyncio
async def test_confirm_upload_returns_false_for_invalid_user_id(dataset_dependencies):
    service, _, _, _ = dataset_dependencies

    result = await service.confirm_upload("not-a-uuid/dataset/v1.csv")

    assert result is False


@pytest.mark.asyncio
async def test_confirm_upload_returns_false_for_invalid_version_component(dataset_dependencies):
    service, _, _, _ = dataset_dependencies

    result = await service.confirm_upload(f"{uuid.uuid4()}/dataset/not-a-version.csv")

    assert result is False


@pytest.mark.asyncio
async def test_confirm_upload_returns_false_when_no_pending_dataset_matches(dataset_dependencies):
    service, _, _, _ = dataset_dependencies

    result = await service.confirm_upload(f"{uuid.uuid4()}/transactions/v1.parquet")

    assert result is False


@pytest.mark.asyncio
async def test_confirm_upload_marks_specific_dataset_version_ready(dataset_dependencies):
    service, dataset_repo, _, _ = dataset_dependencies
    user_id = uuid.uuid4()
    older = Dataset(
        user_id=user_id,
        resource_id=uuid.uuid4(),
        name="forecasting",
        slug="forecasting",
        version=1,
        status="PENDING",
    )
    newer = Dataset(
        user_id=user_id,
        resource_id=uuid.uuid4(),
        name="forecasting",
        slug="forecasting",
        version=2,
        status="PENDING",
    )
    await dataset_repo.create(older)
    await dataset_repo.create(newer)

    result = await service.confirm_upload(f"{user_id}/forecasting/v1.parquet")

    assert result is True
    assert dataset_repo.datasets[older.id].status == "READY"
    assert dataset_repo.datasets[newer.id].status == "PENDING"


@pytest.mark.asyncio
async def test_get_download_url_returns_none_when_ready_dataset_missing(dataset_dependencies):
    service, _, _, _ = dataset_dependencies

    result = await service.get_download_url(uuid.uuid4(), "missing")

    assert result is None


@pytest.mark.asyncio
async def test_get_download_url_returns_signed_url_for_latest_ready_dataset(dataset_dependencies):
    service, dataset_repo, _, storage = dataset_dependencies
    user_id = uuid.uuid4()
    old_dataset = Dataset(
        user_id=user_id,
        resource_id=uuid.uuid4(),
        name="images",
        slug="images",
        version=1,
        status="READY",
        s3_uri=f"s3://{DATASETS_BUCKET}/{user_id}/images/v1.parquet",
    )
    new_dataset = Dataset(
        user_id=user_id,
        resource_id=uuid.uuid4(),
        name="images",
        slug="images",
        version=2,
        status="READY",
        s3_uri=f"s3://{DATASETS_BUCKET}/{user_id}/images/v2.parquet",
    )
    await dataset_repo.create(old_dataset)
    await dataset_repo.create(new_dataset)

    result = await service.get_download_url(user_id, "images")

    assert result == f"https://download.test/{DATASETS_BUCKET}/{user_id}/images/v2.parquet"
    assert storage.download_calls == [(DATASETS_BUCKET, f"{user_id}/images/v2.parquet", 1)]


@pytest.mark.asyncio
async def test_get_version_download_url_returns_none_when_specific_ready_dataset_missing(dataset_dependencies):
    service, _, _, _ = dataset_dependencies

    result = await service.get_version_download_url(uuid.uuid4(), "missing", 9)

    assert result is None


@pytest.mark.asyncio
async def test_get_version_download_url_returns_signed_url_for_specific_version(dataset_dependencies):
    service, dataset_repo, _, storage = dataset_dependencies
    user_id = uuid.uuid4()
    dataset = Dataset(
        user_id=user_id,
        resource_id=uuid.uuid4(),
        name="events",
        slug="events",
        version=3,
        status="READY",
        s3_uri=f"s3://{DATASETS_BUCKET}/{user_id}/events/v3.parquet",
    )
    await dataset_repo.create(dataset)

    result = await service.get_version_download_url(user_id, "events", 3)

    assert result == f"https://download.test/{DATASETS_BUCKET}/{user_id}/events/v3.parquet"
    assert storage.download_calls == [(DATASETS_BUCKET, f"{user_id}/events/v3.parquet", 1)]


@pytest.mark.asyncio
async def test_get_dataset_returns_none_when_missing(dataset_dependencies):
    service, _, _, _ = dataset_dependencies

    result = await service.get_dataset(uuid.uuid4(), "missing", 1)

    assert result is None


@pytest.mark.asyncio
async def test_get_dataset_returns_response_with_resource_labels(dataset_dependencies):
    service, dataset_repo, resource_repo, _ = dataset_dependencies
    user_id = uuid.uuid4()
    resource = Resource(labels={"team": "ml"})
    dataset = Dataset(
        user_id=user_id,
        resource_id=resource.id,
        name="events",
        slug="events",
        version=3,
        status="READY",
        file_type="parquet",
    )
    await resource_repo.create(resource)
    await dataset_repo.create(dataset)

    result = await service.get_dataset(user_id, "events", 3)

    assert result is not None
    assert result.slug == "events"
    assert result.version == 3
    assert result.labels == {"team": "ml"}


@pytest.mark.asyncio
async def test_list_datasets_returns_all_user_datasets_with_fallback_labels(dataset_dependencies):
    service, dataset_repo, resource_repo, _ = dataset_dependencies
    user_id = uuid.uuid4()
    labeled_resource = Resource(labels={"domain": "finance"})
    unlabeled_resource_id = uuid.uuid4()
    await resource_repo.create(labeled_resource)
    await dataset_repo.create(
        Dataset(
            user_id=user_id,
            resource_id=labeled_resource.id,
            name="labels",
            slug="labels",
            version=1,
            status="READY",
        )
    )
    await dataset_repo.create(
        Dataset(
            user_id=user_id,
            resource_id=unlabeled_resource_id,
            name="fallback",
            slug="fallback",
            version=2,
            status="PENDING",
        )
    )

    result = await service.list_datasets(user_id)

    labels_by_slug = {dataset.slug: dataset.labels for dataset in result}
    assert labels_by_slug == {"labels": {"domain": "finance"}, "fallback": {}}
