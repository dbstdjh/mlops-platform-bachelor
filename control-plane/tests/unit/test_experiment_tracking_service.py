import uuid

import pytest

from src.application.experiment_tracking_service import (
    ExperimentTrackingConflictError,
    ExperimentTrackingNotFoundError,
    ExperimentTrackingService,
    ExperimentTrackingValidationError,
)
from src.core.entities.dashboard import RunDashboardCreate, RunDashboardUpdate
from src.core.entities.dataset import Dataset
from src.core.entities.experiment_tracking import Experiment, ExperimentCreate, Run, RunCreate, RunStepBatchCreate
from src.core.entities.model import Model
from src.core.entities.model_repository import ModelRepository
from src.core.entities.resource import Resource


class FakeResourceRepo:
    def __init__(self):
        self.resources: dict[uuid.UUID, Resource] = {}

    async def create(self, resource: Resource) -> Resource:
        self.resources[resource.id] = resource
        return resource

    async def get_by_id(self, resource_id: uuid.UUID) -> Resource | None:
        return self.resources.get(resource_id)

    async def update_labels(self, resource_id: uuid.UUID, labels: dict) -> Resource | None:
        resource = self.resources.get(resource_id)
        if resource is None:
            return None
        updated = resource.model_copy(update={"labels": labels})
        self.resources[resource_id] = updated
        return updated


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
        matches = [run for run in self.runs.values() if run.experiment_id == experiment_id]
        return sorted(matches, key=lambda run: run.number, reverse=True)

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


class FakeRunStepRepo:
    def __init__(self):
        self.steps: dict[tuple[uuid.UUID, int], dict[str, float]] = {}

    async def upsert_batch(self, steps) -> None:
        for step in steps:
            self.steps[(step.run_id, step.step)] = {
                "step": step.step,
                "logged_data": step.logged_data,
                "timestamp": step.timestamp,
            }

    async def get_latest_for_run(self, run_id: uuid.UUID):
        matches = [step for (candidate_run_id, _), step in self.steps.items() if candidate_run_id == run_id]
        if not matches:
            return None
        return max(matches, key=lambda item: item["step"])

    async def list_by_run(self, run_id: uuid.UUID):
        from src.core.entities.experiment_tracking import RunStep

        matches = []
        for (candidate_run_id, step_number), payload in self.steps.items():
            if candidate_run_id == run_id:
                matches.append(
                    RunStep(
                        run_id=run_id,
                        step=step_number,
                        logged_data=payload["logged_data"],
                        timestamp=payload["timestamp"],
                    )
                )
        return sorted(matches, key=lambda step: step.step)


class FakeDatasetRepo:
    def __init__(self):
        self.datasets: dict[uuid.UUID, Dataset] = {}

    async def create(self, dataset: Dataset) -> Dataset:
        self.datasets[dataset.id] = dataset
        return dataset

    async def get_by_id(self, dataset_id: uuid.UUID) -> Dataset | None:
        return self.datasets.get(dataset_id)

    async def get_ready_by_slug_and_version(self, slug: str, user_id: uuid.UUID, version: int) -> Dataset | None:
        for dataset in self.datasets.values():
            if dataset.user_id == user_id and dataset.slug == slug and dataset.version == version and dataset.status == "READY":
                return dataset
        return None


class FakeModelRepo:
    def __init__(self):
        self.models: dict[uuid.UUID, Model] = {}

    async def create(self, model: Model) -> Model:
        self.models[model.id] = model
        return model

    async def get_by_run_id(self, run_id: uuid.UUID) -> Model | None:
        for model in self.models.values():
            if model.run_id == run_id:
                return model
        return None


class FakeModelRepositoryRepo:
    def __init__(self):
        self.repositories: dict[uuid.UUID, ModelRepository] = {}

    async def create(self, repo: ModelRepository) -> ModelRepository:
        self.repositories[repo.id] = repo
        return repo

    async def get_by_id(self, repository_id: uuid.UUID) -> ModelRepository | None:
        return self.repositories.get(repository_id)


class FakeDashboardRepo:
    def __init__(self):
        self.items: dict[uuid.UUID, dict] = {}

    async def create_run_dashboard(self, dashboard, *, run_id: uuid.UUID, display_order: int):
        record = {
            "id": dashboard.id,
            "run_id": run_id,
            "title": dashboard.name,
            "plot_type": dashboard.config_data["plot_type"],
            "metrics": list(dashboard.config_data["metrics"]),
            "display_order": display_order,
            "grafana_uid": dashboard.grafana_uid,
            "created_at": dashboard.created_at,
        }
        self.items[dashboard.id] = record
        from src.core.entities.dashboard import RunDashboardRecord

        return RunDashboardRecord(**record)

    async def list_by_run(self, run_id: uuid.UUID):
        from src.core.entities.dashboard import RunDashboardRecord

        matches = [RunDashboardRecord(**item) for item in self.items.values() if item["run_id"] == run_id]
        return sorted(matches, key=lambda item: (item.display_order, item.created_at))

    async def get_by_id_for_run(self, run_id: uuid.UUID, dashboard_id: uuid.UUID):
        from src.core.entities.dashboard import RunDashboardRecord

        item = self.items.get(dashboard_id)
        if not item or item["run_id"] != run_id:
            return None
        return RunDashboardRecord(**item)

    async def update_run_dashboard(self, run_id: uuid.UUID, dashboard_id: uuid.UUID, **updates):
        from src.core.entities.dashboard import RunDashboardRecord

        item = self.items.get(dashboard_id)
        if not item or item["run_id"] != run_id:
            return None
        if updates.get("name") is not None:
            item["title"] = updates["name"]
        if updates.get("grafana_uid") is not None:
            item["grafana_uid"] = updates["grafana_uid"]
        if updates.get("config_data") is not None:
            item["plot_type"] = updates["config_data"]["plot_type"]
            item["metrics"] = list(updates["config_data"]["metrics"])
        if updates.get("display_order") is not None:
            item["display_order"] = updates["display_order"]
        self.items[dashboard_id] = item
        return RunDashboardRecord(**item)

    async def delete_run_dashboard(self, run_id: uuid.UUID, dashboard_id: uuid.UUID) -> bool:
        item = self.items.get(dashboard_id)
        if not item or item["run_id"] != run_id:
            return False
        del self.items[dashboard_id]
        return True


class FakeGrafanaClient:
    def __init__(self):
        self.deleted: list[str] = []
        self.upserts: list[dict] = []

    async def upsert_run_plot(self, **kwargs):
        self.upserts.append(kwargs)
        return kwargs["grafana_uid"] or f"grafana-{len(self.upserts)}"

    async def delete_dashboard(self, grafana_uid: str) -> None:
        self.deleted.append(grafana_uid)

    def build_solo_iframe_url(self, grafana_uid: str) -> str:
        return f"http://grafana.local/d-solo/{grafana_uid}/run-plot?panelId=1"


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture
def tracking_dependencies():
    experiment_repo = FakeExperimentRepo()
    run_repo = FakeRunRepo()
    run_step_repo = FakeRunStepRepo()
    resource_repo = FakeResourceRepo()
    dataset_repo = FakeDatasetRepo()
    model_repo = FakeModelRepo()
    model_repository_repo = FakeModelRepositoryRepo()
    dashboard_repo = FakeDashboardRepo()
    grafana_client = FakeGrafanaClient()
    session = FakeSession()
    service = ExperimentTrackingService(
        experiment_repo=experiment_repo,
        run_repo=run_repo,
        run_step_repo=run_step_repo,
        resource_repo=resource_repo,
        dataset_repo=dataset_repo,
        model_repo=model_repo,
        model_repository_repo=model_repository_repo,
        dashboard_repo=dashboard_repo,
        grafana_client=grafana_client,
        session=session,
    )
    return service, experiment_repo, run_repo, run_step_repo, resource_repo, dataset_repo, model_repo, model_repository_repo, dashboard_repo, grafana_client, session


@pytest.mark.asyncio
async def test_create_experiment_generates_unique_slug(tracking_dependencies):
    service, _, _, _, _, _, _, _, _, _, _ = tracking_dependencies
    user_id = uuid.uuid4()

    first = await service.create_experiment(user_id, ExperimentCreate(name="Vision Models", logged_data_template=["loss"]))
    second = await service.create_experiment(user_id, ExperimentCreate(name="Vision   Models!!!", logged_data_template=["loss"]))

    assert first.slug == "vision-models"
    assert second.slug == "vision-models-2"


@pytest.mark.asyncio
async def test_start_run_assigns_sequential_numbers_and_resolves_dataset(tracking_dependencies):
    service, experiment_repo, _, _, resource_repo, dataset_repo, _, _, _, _, _ = tracking_dependencies
    user_id = uuid.uuid4()
    experiment_resource = Resource()
    dataset_resource = Resource()
    await resource_repo.create(experiment_resource)
    await resource_repo.create(dataset_resource)
    await experiment_repo.create(
        Experiment(user_id=user_id, resource_id=experiment_resource.id, name="training", slug="training", logged_data_template=["loss"])
    )
    await dataset_repo.create(
        Dataset(user_id=user_id, resource_id=dataset_resource.id, name="events", slug="events", version=2, status="READY")
    )

    first = await service.start_run(user_id, "training", RunCreate())
    second = await service.start_run(user_id, "training", RunCreate(dataset_slug="events", dataset_version=2))

    assert first.run_number == 1
    assert second.run_number == 2
    assert second.dataset is not None
    assert second.dataset.dataset_slug == "events"


@pytest.mark.asyncio
async def test_create_experiment_and_start_run_commit_immediately(tracking_dependencies):
    service, _, _, _, _, _, _, _, _, _, session = tracking_dependencies
    user_id = uuid.uuid4()

    created = await service.create_experiment(
        user_id,
        ExperimentCreate(name="Dense Metrics", logged_data_template=["loss"]),
    )
    started = await service.start_run(user_id, created.slug, RunCreate())

    assert created.slug == "dense-metrics"
    assert started.run_number == 1
    assert session.commits == 2


@pytest.mark.asyncio
async def test_start_run_raises_when_dataset_missing(tracking_dependencies):
    service, experiment_repo, _, _, resource_repo, _, _, _, _, _, _ = tracking_dependencies
    user_id = uuid.uuid4()
    experiment_resource = Resource()
    await resource_repo.create(experiment_resource)
    await experiment_repo.create(
        Experiment(user_id=user_id, resource_id=experiment_resource.id, name="training", slug="training", logged_data_template=["loss"])
    )

    with pytest.raises(ExperimentTrackingNotFoundError, match="Dataset not found"):
        await service.start_run(user_id, "training", RunCreate(dataset_slug="events", dataset_version=2))


@pytest.mark.asyncio
async def test_append_run_steps_validates_metrics_and_overwrites_duplicate_steps(tracking_dependencies):
    service, experiment_repo, run_repo, run_step_repo, resource_repo, _, _, _, _, _, _ = tracking_dependencies
    user_id = uuid.uuid4()
    experiment_resource = Resource()
    run_resource = Resource(labels={"lr": 0.01})
    await resource_repo.create(experiment_resource)
    await resource_repo.create(run_resource)
    experiment = Experiment(
        user_id=user_id,
        resource_id=experiment_resource.id,
        name="training",
        slug="training",
        logged_data_template=["loss", "accuracy"],
    )
    run = Run(resource_id=run_resource.id, experiment_id=experiment.id, number=1)
    await experiment_repo.create(experiment)
    await run_repo.create(run)

    with pytest.raises(ExperimentTrackingValidationError, match="Metrics not declared"):
        await service.append_run_steps(
            user_id,
            "training",
            1,
            RunStepBatchCreate(items=[{"step": 0, "logged_data": {"precision": 0.9}}]),
        )

    await service.append_run_steps(
        user_id,
        "training",
        1,
        RunStepBatchCreate(
            items=[
                {"step": 0, "logged_data": {"loss": 1.0}},
                {"step": 1, "logged_data": {"loss": 0.8}},
                {"step": 1, "logged_data": {"loss": 0.7, "accuracy": 0.9}},
            ]
        ),
    )

    steps = await run_step_repo.list_by_run(run.id)
    assert len(steps) == 2
    assert steps[1].logged_data == {"loss": 0.7, "accuracy": 0.9}

    run_response = await service.get_run(user_id, "training", 1)
    assert run_response is not None
    assert run_response.latest_metrics == {"loss": 0.7, "accuracy": 0.9}
    assert run_response.labels == {"lr": 0.01}


@pytest.mark.asyncio
async def test_terminal_transition_blocks_further_logging(tracking_dependencies):
    service, experiment_repo, run_repo, _, resource_repo, _, _, _, _, _, _ = tracking_dependencies
    user_id = uuid.uuid4()
    experiment_resource = Resource()
    run_resource = Resource()
    await resource_repo.create(experiment_resource)
    await resource_repo.create(run_resource)
    experiment = Experiment(
        user_id=user_id,
        resource_id=experiment_resource.id,
        name="training",
        slug="training",
        logged_data_template=["loss"],
    )
    run = Run(resource_id=run_resource.id, experiment_id=experiment.id, number=1)
    await experiment_repo.create(experiment)
    await run_repo.create(run)

    completed = await service.complete_run(user_id, "training", 1)
    assert completed.status == "COMPLETED"

    with pytest.raises(ExperimentTrackingConflictError, match="already terminal"):
        await service.append_run_steps(
            user_id,
            "training",
            1,
            RunStepBatchCreate(items=[{"step": 2, "logged_data": {"loss": 0.4}}]),
        )


@pytest.mark.asyncio
async def test_plot_responses_are_chart_ready_and_include_model_ref(tracking_dependencies):
    service, experiment_repo, run_repo, run_step_repo, resource_repo, _, model_repo, model_repository_repo, _, _, _ = tracking_dependencies
    user_id = uuid.uuid4()
    experiment_resource = Resource(labels={"team": "ml"})
    run_one_resource = Resource()
    run_two_resource = Resource()
    repo_resource = Resource()
    model_resource = Resource()
    await resource_repo.create(experiment_resource)
    await resource_repo.create(run_one_resource)
    await resource_repo.create(run_two_resource)
    await resource_repo.create(repo_resource)
    await resource_repo.create(model_resource)
    experiment = Experiment(
        user_id=user_id,
        resource_id=experiment_resource.id,
        name="training",
        slug="training",
        logged_data_template=["loss"],
    )
    run_one = Run(resource_id=run_one_resource.id, experiment_id=experiment.id, number=1)
    run_two = Run(resource_id=run_two_resource.id, experiment_id=experiment.id, number=2)
    repository = ModelRepository(user_id=user_id, resource_id=repo_resource.id, name="models", slug="models")
    model = Model(resource_id=model_resource.id, repository_id=repository.id, run_id=run_two.id, name="detector", version="1.0")
    await experiment_repo.create(experiment)
    await run_repo.create(run_one)
    await run_repo.create(run_two)
    await model_repository_repo.create(repository)
    await model_repo.create(model)
    await run_step_repo.upsert_batch(
        [
            type("Step", (), {"run_id": run_one.id, "step": 0, "logged_data": {"loss": 1.1}, "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}),
            type("Step", (), {"run_id": run_one.id, "step": 1, "logged_data": {"loss": 0.9}, "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}),
            type("Step", (), {"run_id": run_two.id, "step": 0, "logged_data": {"loss": 1.2}, "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}),
        ]
    )

    experiment_response = await service.get_experiment(user_id, "training")
    run_plot = await service.get_run_metric_plot(user_id, "training", 1, "loss")
    experiment_plot = await service.get_experiment_metric_plot(user_id, "training", "loss")

    assert experiment_response is not None
    assert experiment_response.latest_run is not None
    assert experiment_response.latest_run.run_number == 2
    assert experiment_response.latest_run.model is not None
    assert experiment_response.latest_run.model.repository_slug == "models"
    assert [point.step for point in run_plot.points] == [0, 1]
    assert [series.run.run_number for series in experiment_plot.series] == [1, 2]


@pytest.mark.asyncio
async def test_run_dashboards_are_persisted_validated_and_reordered(tracking_dependencies):
    service, experiment_repo, run_repo, _, resource_repo, _, _, _, _, grafana_client, _ = tracking_dependencies
    user_id = uuid.uuid4()
    experiment_resource = Resource()
    run_resource = Resource()
    await resource_repo.create(experiment_resource)
    await resource_repo.create(run_resource)
    experiment = Experiment(
        user_id=user_id,
        resource_id=experiment_resource.id,
        name="training",
        slug="training",
        logged_data_template=["loss", "accuracy", "f1"],
    )
    run = Run(resource_id=run_resource.id, experiment_id=experiment.id, number=1)
    await experiment_repo.create(experiment)
    await run_repo.create(run)

    created = await service.create_run_dashboard(
        user_id,
        "training",
        1,
        RunDashboardCreate(title="Loss panel", plot_type="line", metrics=["loss", "accuracy"]),
    )
    assert created.metrics == ["loss", "accuracy"]
    assert created.display_order == 0
    assert created.iframe_url.endswith("grafana-1/run-plot?panelId=1")

    second = await service.create_run_dashboard(
        user_id,
        "training",
        1,
        RunDashboardCreate(title="F1 stat", plot_type="stat", metrics=["f1"]),
    )
    assert second.display_order == 1

    updated = await service.update_run_dashboard(
        user_id,
        "training",
        1,
        second.id,
        RunDashboardUpdate(display_order=0, title="F1 latest"),
    )
    assert updated.display_order == 0

    listed = await service.list_run_dashboards(user_id, "training", 1)
    assert [item.title for item in listed] == ["F1 latest", "Loss panel"]
    assert grafana_client.upserts[-1]["title"] == "F1 latest"


@pytest.mark.asyncio
async def test_run_dashboard_validation_and_limit_are_enforced(tracking_dependencies):
    service, experiment_repo, run_repo, _, resource_repo, _, _, _, _, _, _ = tracking_dependencies
    user_id = uuid.uuid4()
    experiment_resource = Resource()
    run_resource = Resource()
    await resource_repo.create(experiment_resource)
    await resource_repo.create(run_resource)
    experiment = Experiment(
        user_id=user_id,
        resource_id=experiment_resource.id,
        name="training",
        slug="training",
        logged_data_template=["loss", "accuracy", "f1", "precision"],
    )
    run = Run(resource_id=run_resource.id, experiment_id=experiment.id, number=1)
    await experiment_repo.create(experiment)
    await run_repo.create(run)

    with pytest.raises(ExperimentTrackingValidationError, match="Metrics not declared"):
        await service.create_run_dashboard(
            user_id,
            "training",
            1,
            RunDashboardCreate(title="Bad", plot_type="line", metrics=["roc_auc"]),
        )

    for index, metric in enumerate(["loss", "accuracy", "f1", "precision"], start=1):
        created = await service.create_run_dashboard(
            user_id,
            "training",
            1,
            RunDashboardCreate(title=f"Plot {index}", plot_type="stat", metrics=[metric]),
        )
        assert created.display_order == index - 1

    with pytest.raises(ExperimentTrackingValidationError, match="up to 4 saved plots"):
        await service.create_run_dashboard(
            user_id,
            "training",
            1,
            RunDashboardCreate(title="Overflow", plot_type="stat", metrics=["loss"]),
        )
