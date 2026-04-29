"""
Application service: Experiment Tracking and training observability.
"""

import uuid
from collections import OrderedDict
from datetime import datetime, timezone

from src.core.entities.experiment_tracking import (
    DatasetRef,
    Experiment,
    ExperimentCreate,
    ExperimentMetricResponse,
    ExperimentMetricSeries,
    ExperimentMetricsResponse,
    ExperimentResponse,
    ModelRef,
    PlotPoint,
    Run,
    RunCreate,
    RunMetricResponse,
    RunRef,
    RunResponse,
    RunStep,
    RunStepBatchCreate,
    RunSummaryResponse,
)
from src.core.entities.resource import Resource
from src.core.ports.repositories import (
    DatasetRepo,
    ExperimentRepo,
    ModelRepo,
    ModelRepositoryRepo,
    ResourceRepository,
    RunRepo,
    RunStepRepo,
)
from src.core.slugging import slug_candidate, slugify


class ExperimentTrackingNotFoundError(Exception):
    """Raised when an experiment-tracking resource cannot be found."""


class ExperimentTrackingConflictError(Exception):
    """Raised when a state transition conflicts with the current resource state."""


class ExperimentTrackingValidationError(Exception):
    """Raised when a request violates business rules."""


class ExperimentTrackingService:
    """Owns experiment lifecycle, run lifecycle, and training observability."""

    def __init__(
        self,
        experiment_repo: ExperimentRepo,
        run_repo: RunRepo,
        run_step_repo: RunStepRepo,
        resource_repo: ResourceRepository,
        dataset_repo: DatasetRepo,
        model_repo: ModelRepo,
        model_repository_repo: ModelRepositoryRepo,
    ):
        self._experiment_repo = experiment_repo
        self._run_repo = run_repo
        self._run_step_repo = run_step_repo
        self._resource_repo = resource_repo
        self._dataset_repo = dataset_repo
        self._model_repo = model_repo
        self._model_repository_repo = model_repository_repo

    async def create_experiment(self, user_id: uuid.UUID, data: ExperimentCreate) -> ExperimentResponse:
        slug = await self._generate_unique_slug(user_id, data.name)
        resource = Resource(labels=data.labels)
        await self._resource_repo.create(resource)

        experiment = Experiment(
            user_id=user_id,
            resource_id=resource.id,
            name=data.name,
            slug=slug,
            logged_data_template=data.logged_data_template,
        )
        await self._experiment_repo.create(experiment)
        return await self._build_experiment_response(experiment)

    async def list_experiments(self, user_id: uuid.UUID) -> list[ExperimentResponse]:
        experiments = await self._experiment_repo.list_by_user(user_id)
        return [await self._build_experiment_response(experiment) for experiment in experiments]

    async def get_experiment(self, user_id: uuid.UUID, experiment_slug: str) -> ExperimentResponse | None:
        experiment = await self._experiment_repo.get_by_slug(user_id, experiment_slug)
        if not experiment:
            return None
        return await self._build_experiment_response(experiment)

    async def start_run(self, user_id: uuid.UUID, experiment_slug: str, data: RunCreate) -> RunResponse:
        experiment = await self._get_experiment_or_raise(user_id, experiment_slug)
        dataset_id = await self._resolve_dataset_id(user_id, data)

        resource = Resource(labels=data.labels)
        await self._resource_repo.create(resource)

        run = Run(
            resource_id=resource.id,
            experiment_id=experiment.id,
            dataset_id=dataset_id,
            number=await self._run_repo.get_next_number(experiment.id),
            status="RUNNING",
        )
        await self._run_repo.create(run)
        return await self._build_run_response(experiment, run)

    async def list_runs(self, user_id: uuid.UUID, experiment_slug: str) -> list[RunResponse]:
        experiment = await self._get_experiment_or_raise(user_id, experiment_slug)
        runs = await self._run_repo.list_by_experiment(experiment.id)
        return [await self._build_run_response(experiment, run) for run in runs]

    async def get_run(self, user_id: uuid.UUID, experiment_slug: str, run_number: int) -> RunResponse | None:
        experiment = await self._experiment_repo.get_by_slug(user_id, experiment_slug)
        if not experiment:
            return None
        run = await self._run_repo.get_by_number(experiment.id, run_number)
        if not run:
            return None
        return await self._build_run_response(experiment, run)

    async def append_run_steps(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        run_number: int,
        data: RunStepBatchCreate,
    ) -> None:
        experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        self._ensure_run_is_running(run)

        normalized_items = self._normalize_step_items(experiment, data)
        steps = [
            RunStep(
                run_id=run.id,
                step=item.step,
                logged_data={metric_name: float(metric_value) for metric_name, metric_value in item.logged_data.items()},
                timestamp=item.timestamp or datetime.now(timezone.utc),
            )
            for item in normalized_items
        ]
        await self._run_step_repo.upsert_batch(steps)

    async def complete_run(self, user_id: uuid.UUID, experiment_slug: str, run_number: int) -> RunResponse:
        experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        self._ensure_run_is_running(run)
        updated = await self._run_repo.update_status(run.id, "COMPLETED", ended_at=datetime.now(timezone.utc))
        if not updated:
            raise ExperimentTrackingNotFoundError("Run not found")
        return await self._build_run_response(experiment, updated)

    async def fail_run(self, user_id: uuid.UUID, experiment_slug: str, run_number: int) -> RunResponse:
        experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        self._ensure_run_is_running(run)
        updated = await self._run_repo.update_status(run.id, "FAILED", ended_at=datetime.now(timezone.utc))
        if not updated:
            raise ExperimentTrackingNotFoundError("Run not found")
        return await self._build_run_response(experiment, updated)

    async def get_metrics(self, user_id: uuid.UUID, experiment_slug: str) -> ExperimentMetricsResponse:
        experiment = await self._get_experiment_or_raise(user_id, experiment_slug)
        return ExperimentMetricsResponse(metrics=experiment.logged_data_template)

    async def get_experiment_metric_plot(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        metric_name: str,
    ) -> ExperimentMetricResponse:
        experiment = await self._get_experiment_or_raise(user_id, experiment_slug)
        self._ensure_metric_is_defined(experiment, metric_name)

        runs = await self._run_repo.list_by_experiment(experiment.id)
        series: list[ExperimentMetricSeries] = []
        for run in reversed(runs):
            points = await self._build_plot_points(run.id, metric_name)
            series.append(
                ExperimentMetricSeries(
                    run=RunRef(experiment_slug=experiment.slug, run_number=run.number),
                    points=points,
                )
            )
        return ExperimentMetricResponse(metric_name=metric_name, series=series)

    async def get_run_metric_plot(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        run_number: int,
        metric_name: str,
    ) -> RunMetricResponse:
        experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        self._ensure_metric_is_defined(experiment, metric_name)
        return RunMetricResponse(
            metric_name=metric_name,
            points=await self._build_plot_points(run.id, metric_name),
        )

    async def _build_experiment_response(self, experiment: Experiment) -> ExperimentResponse:
        resource = await self._resource_repo.get_by_id(experiment.resource_id)
        runs = await self._run_repo.list_by_experiment(experiment.id)
        latest_run = await self._build_run_summary(experiment, runs[0]) if runs else None
        return ExperimentResponse(
            name=experiment.name,
            slug=experiment.slug,
            logged_data_template=experiment.logged_data_template,
            created_at=experiment.created_at,
            labels=resource.labels if resource else {},
            run_count=len(runs),
            latest_run=latest_run,
        )

    async def _build_run_response(self, experiment: Experiment, run: Run) -> RunResponse:
        summary = await self._build_run_summary(experiment, run)
        return RunResponse(
            experiment_slug=experiment.slug,
            run_number=summary.run_number,
            status=summary.status,
            created_at=summary.created_at,
            ended_at=summary.ended_at,
            dataset=summary.dataset,
            model=summary.model,
            latest_metrics=summary.latest_metrics,
            labels=summary.labels,
        )

    async def _build_run_summary(self, experiment: Experiment, run: Run) -> RunSummaryResponse:
        resource = await self._resource_repo.get_by_id(run.resource_id)
        steps = await self._run_step_repo.list_by_run(run.id)
        latest_metrics = self._latest_metrics_from_steps(steps)

        dataset_ref = None
        if run.dataset_id:
            dataset = await self._dataset_repo.get_by_id(run.dataset_id)
            if dataset:
                dataset_ref = DatasetRef(dataset_slug=dataset.slug, version=dataset.version)

        model_ref = None
        model = await self._model_repo.get_by_run_id(run.id)
        if model:
            repository = await self._model_repository_repo.get_by_id(model.repository_id)
            if repository:
                model_ref = ModelRef(repository_slug=repository.slug, version=model.version)

        return RunSummaryResponse(
            run_number=run.number,
            status=run.status,
            created_at=run.created_at,
            ended_at=run.ended_at,
            dataset=dataset_ref,
            model=model_ref,
            latest_metrics=latest_metrics,
            labels=resource.labels if resource else {},
        )

    async def _build_plot_points(self, run_id: uuid.UUID, metric_name: str) -> list[PlotPoint]:
        steps = await self._run_step_repo.list_by_run(run_id)
        points: list[PlotPoint] = []
        for step in steps:
            if metric_name in step.logged_data:
                points.append(
                    PlotPoint(
                        step=step.step,
                        val=float(step.logged_data[metric_name]),
                        timestamp=step.timestamp,
                    )
                )
        return points

    async def _resolve_dataset_id(self, user_id: uuid.UUID, data: RunCreate) -> uuid.UUID | None:
        if data.dataset_slug is None:
            return None
        dataset = await self._dataset_repo.get_ready_by_slug_and_version(
            data.dataset_slug,
            user_id,
            data.dataset_version,
        )
        if not dataset:
            raise ExperimentTrackingNotFoundError("Dataset not found")
        return dataset.id

    async def _get_experiment_or_raise(self, user_id: uuid.UUID, experiment_slug: str) -> Experiment:
        experiment = await self._experiment_repo.get_by_slug(user_id, experiment_slug)
        if not experiment:
            raise ExperimentTrackingNotFoundError("Experiment not found")
        return experiment

    async def _get_experiment_and_run_or_raise(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        run_number: int,
    ) -> tuple[Experiment, Run]:
        experiment = await self._get_experiment_or_raise(user_id, experiment_slug)
        run = await self._run_repo.get_by_number(experiment.id, run_number)
        if not run:
            raise ExperimentTrackingNotFoundError("Run not found")
        return experiment, run

    def _normalize_step_items(self, experiment: Experiment, data: RunStepBatchCreate):
        normalized_items: "OrderedDict[int, object]" = OrderedDict()
        for item in data.items:
            self._validate_logged_data_template(experiment, item.logged_data)
            normalized_items[item.step] = item
        return list(normalized_items.values())

    def _validate_logged_data_template(self, experiment: Experiment, logged_data: dict[str, float | int]) -> None:
        invalid_metrics = sorted(set(logged_data) - set(experiment.logged_data_template))
        if invalid_metrics:
            raise ExperimentTrackingValidationError(
                f"Metrics not declared by experiment: {', '.join(invalid_metrics)}"
            )

    def _ensure_metric_is_defined(self, experiment: Experiment, metric_name: str) -> None:
        if metric_name not in experiment.logged_data_template:
            raise ExperimentTrackingValidationError("Metric is not declared by the experiment")

    def _ensure_run_is_running(self, run: Run) -> None:
        if run.status != "RUNNING":
            raise ExperimentTrackingConflictError("Run is already terminal")

    def _latest_metrics_from_steps(self, steps: list[RunStep]) -> dict[str, float]:
        latest_metrics: dict[str, float] = {}
        for step in steps:
            for metric_name, metric_value in step.logged_data.items():
                latest_metrics[metric_name] = float(metric_value)
        return latest_metrics

    async def _generate_unique_slug(self, user_id: uuid.UUID, name: str) -> str:
        base_slug = slugify(name)
        index = 1
        while True:
            candidate = slug_candidate(base_slug, index)
            if not await self._experiment_repo.slug_exists(user_id, candidate):
                return candidate
            index += 1
