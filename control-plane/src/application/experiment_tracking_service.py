"""
Application service: Experiment Tracking and training observability.
"""

import uuid
from collections import OrderedDict
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.entities.dashboard import Dashboard, RunDashboardCreate, RunDashboardResponse, RunDashboardUpdate
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
from src.core.entities.pagination import PaginatedResponse, SortDirection, page_items
from src.core.entities.resource import Resource
from src.core.ports.observability import GrafanaDashboardClient
from src.core.ports.repositories import (
    DashboardRepo,
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
        dashboard_repo: DashboardRepo,
        grafana_client: GrafanaDashboardClient,
        session: AsyncSession | None = None,
    ):
        self._experiment_repo = experiment_repo
        self._run_repo = run_repo
        self._run_step_repo = run_step_repo
        self._resource_repo = resource_repo
        self._dataset_repo = dataset_repo
        self._model_repo = model_repo
        self._model_repository_repo = model_repository_repo
        self._dashboard_repo = dashboard_repo
        self._grafana_client = grafana_client
        self._session = session

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
        await self._commit_session()
        return await self._build_experiment_response(experiment)

    async def list_experiments(self, user_id: uuid.UUID) -> list[ExperimentResponse]:
        experiments = await self._experiment_repo.list_by_user(user_id)
        return [await self._build_experiment_response(experiment) for experiment in experiments]

    async def list_experiments_page(
        self,
        user_id: uuid.UUID,
        *,
        search: str | None,
        sort_by: str,
        sort_dir: SortDirection,
        limit: int,
        offset: int,
    ) -> PaginatedResponse[ExperimentResponse]:
        """List experiments with dashboard-oriented filtering and pagination."""
        return page_items(
            await self.list_experiments(user_id),
            search=search,
            search_fields=[
                lambda item: item.name,
                lambda item: item.slug,
                lambda item: " ".join(item.logged_data_template),
                lambda item: item.latest_run.status if item.latest_run else "",
            ],
            sort_by=sort_by,
            sort_dir=sort_dir,
            sort_fields={
                "name": lambda item: item.name,
                "slug": lambda item: item.slug,
                "run_count": lambda item: item.run_count,
                "created_at": lambda item: item.created_at,
            },
            limit=limit,
            offset=offset,
        )

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
        await self._commit_session()
        return await self._build_run_response(experiment, run)

    async def list_runs(self, user_id: uuid.UUID, experiment_slug: str) -> list[RunResponse]:
        experiment = await self._get_experiment_or_raise(user_id, experiment_slug)
        runs = await self._run_repo.list_by_experiment(experiment.id)
        return [await self._build_run_response(experiment, run) for run in runs]

    async def list_runs_page(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        *,
        search: str | None,
        sort_by: str,
        sort_dir: SortDirection,
        limit: int,
        offset: int,
    ) -> PaginatedResponse[RunResponse]:
        """List runs with dashboard-oriented filtering and pagination."""
        return page_items(
            await self.list_runs(user_id, experiment_slug),
            search=search,
            search_fields=[
                lambda item: item.run_number,
                lambda item: item.status,
                lambda item: item.dataset.dataset_slug if item.dataset else "",
                lambda item: item.model.repository_slug if item.model else "",
            ],
            sort_by=sort_by,
            sort_dir=sort_dir,
            sort_fields={
                "run_number": lambda item: item.run_number,
                "status": lambda item: item.status,
                "created_at": lambda item: item.created_at,
                "ended_at": lambda item: item.ended_at,
            },
            limit=limit,
            offset=offset,
        )

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
        await self._commit_session()

    async def complete_run(self, user_id: uuid.UUID, experiment_slug: str, run_number: int) -> RunResponse:
        experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        self._ensure_run_is_running(run)
        updated = await self._run_repo.update_status(run.id, "COMPLETED", ended_at=datetime.now(timezone.utc))
        if not updated:
            raise ExperimentTrackingNotFoundError("Run not found")
        await self._commit_session()
        return await self._build_run_response(experiment, updated)

    async def fail_run(self, user_id: uuid.UUID, experiment_slug: str, run_number: int) -> RunResponse:
        experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        self._ensure_run_is_running(run)
        updated = await self._run_repo.update_status(run.id, "FAILED", ended_at=datetime.now(timezone.utc))
        if not updated:
            raise ExperimentTrackingNotFoundError("Run not found")
        await self._commit_session()
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

    async def list_run_dashboards(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        run_number: int,
    ) -> list[RunDashboardResponse]:
        _experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        dashboards = await self._dashboard_repo.list_by_run(run.id)
        return [self._build_run_dashboard_response(item) for item in dashboards]

    async def create_run_dashboard(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        run_number: int,
        data: RunDashboardCreate,
    ) -> RunDashboardResponse:
        experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        self._ensure_requested_metrics_are_defined(experiment, data.metrics)

        existing = await self._dashboard_repo.list_by_run(run.id)
        if len(existing) >= 4:
            raise ExperimentTrackingValidationError("A run can only have up to 4 saved plots")

        grafana_uid = await self._grafana_client.upsert_run_plot(
            grafana_uid=None,
            title=data.title,
            run_id=run.id,
            plot_type=data.plot_type,
            metrics=data.metrics,
        )
        dashboard = Dashboard(
            name=data.title,
            grafana_uid=grafana_uid,
            config_data={"plot_type": data.plot_type, "metrics": data.metrics},
        )

        try:
            created = await self._dashboard_repo.create_run_dashboard(
                dashboard,
                run_id=run.id,
                display_order=len(existing),
            )
            await self._commit_session()
        except Exception:
            await self._rollback_session()
            await self._grafana_client.delete_dashboard(grafana_uid)
            raise

        return self._build_run_dashboard_response(created)

    async def update_run_dashboard(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        run_number: int,
        dashboard_id: uuid.UUID,
        data: RunDashboardUpdate,
    ) -> RunDashboardResponse:
        experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        existing = await self._dashboard_repo.get_by_id_for_run(run.id, dashboard_id)
        if not existing:
            raise ExperimentTrackingNotFoundError("Run dashboard not found")

        final_title = data.title or existing.title
        final_plot_type = data.plot_type or existing.plot_type
        final_metrics = data.metrics or existing.metrics
        candidate = RunDashboardCreate(title=final_title, plot_type=final_plot_type, metrics=final_metrics)
        self._ensure_requested_metrics_are_defined(experiment, candidate.metrics)

        grafana_changed = (
            candidate.title != existing.title
            or candidate.plot_type != existing.plot_type
            or candidate.metrics != existing.metrics
        )
        if grafana_changed:
            await self._grafana_client.upsert_run_plot(
                grafana_uid=existing.grafana_uid,
                title=candidate.title,
                run_id=run.id,
                plot_type=candidate.plot_type,
                metrics=candidate.metrics,
            )

        try:
            updated = await self._dashboard_repo.update_run_dashboard(
                run.id,
                dashboard_id,
                name=candidate.title,
                grafana_uid=existing.grafana_uid,
                config_data={"plot_type": candidate.plot_type, "metrics": candidate.metrics},
            )
            if not updated:
                raise ExperimentTrackingNotFoundError("Run dashboard not found")

            if data.display_order is not None:
                updated = await self._reorder_run_dashboards(run.id, dashboard_id, data.display_order)

            await self._commit_session()
        except Exception:
            await self._rollback_session()
            if grafana_changed:
                await self._grafana_client.upsert_run_plot(
                    grafana_uid=existing.grafana_uid,
                    title=existing.title,
                    run_id=run.id,
                    plot_type=existing.plot_type,
                    metrics=existing.metrics,
                )
            raise

        return self._build_run_dashboard_response(updated)

    async def delete_run_dashboard(
        self,
        user_id: uuid.UUID,
        experiment_slug: str,
        run_number: int,
        dashboard_id: uuid.UUID,
    ) -> None:
        _experiment, run = await self._get_experiment_and_run_or_raise(user_id, experiment_slug, run_number)
        existing = await self._dashboard_repo.get_by_id_for_run(run.id, dashboard_id)
        if not existing:
            raise ExperimentTrackingNotFoundError("Run dashboard not found")

        if existing.grafana_uid:
            await self._grafana_client.delete_dashboard(existing.grafana_uid)

        try:
            deleted = await self._dashboard_repo.delete_run_dashboard(run.id, dashboard_id)
            if not deleted:
                raise ExperimentTrackingNotFoundError("Run dashboard not found")
            await self._reindex_run_dashboards(run.id)
            await self._commit_session()
        except Exception:
            await self._rollback_session()
            if existing.grafana_uid:
                await self._grafana_client.upsert_run_plot(
                    grafana_uid=existing.grafana_uid,
                    title=existing.title,
                    run_id=run.id,
                    plot_type=existing.plot_type,
                    metrics=existing.metrics,
                )
            raise

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

    def _build_run_dashboard_response(self, dashboard) -> RunDashboardResponse:
        if not dashboard.grafana_uid:
            raise ExperimentTrackingValidationError("Saved run plot is missing a Grafana UID")
        return RunDashboardResponse(
            id=dashboard.id,
            title=dashboard.title,
            plot_type=dashboard.plot_type,
            metrics=dashboard.metrics,
            display_order=dashboard.display_order,
            iframe_url=self._grafana_client.build_solo_iframe_url(dashboard.grafana_uid),
            created_at=dashboard.created_at,
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

    def _ensure_requested_metrics_are_defined(self, experiment: Experiment, metric_names: list[str]) -> None:
        invalid_metrics = sorted(set(metric_names) - set(experiment.logged_data_template))
        if invalid_metrics:
            raise ExperimentTrackingValidationError(
                f"Metrics not declared by experiment: {', '.join(invalid_metrics)}"
            )

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

    async def _reorder_run_dashboards(self, run_id: uuid.UUID, dashboard_id: uuid.UUID, target_index: int):
        dashboards = await self._dashboard_repo.list_by_run(run_id)
        if not dashboards:
            raise ExperimentTrackingNotFoundError("Run dashboard not found")

        target_index = max(0, min(target_index, len(dashboards) - 1))
        moved = next((item for item in dashboards if item.id == dashboard_id), None)
        if not moved:
            raise ExperimentTrackingNotFoundError("Run dashboard not found")

        reordered = [item for item in dashboards if item.id != dashboard_id]
        reordered.insert(target_index, moved)
        for index, item in enumerate(reordered):
            await self._dashboard_repo.update_run_dashboard(run_id, item.id, display_order=index)

        refreshed = await self._dashboard_repo.get_by_id_for_run(run_id, dashboard_id)
        if not refreshed:
            raise ExperimentTrackingNotFoundError("Run dashboard not found")
        return refreshed

    async def _reindex_run_dashboards(self, run_id: uuid.UUID) -> None:
        dashboards = await self._dashboard_repo.list_by_run(run_id)
        for index, dashboard in enumerate(dashboards):
            if dashboard.display_order != index:
                await self._dashboard_repo.update_run_dashboard(run_id, dashboard.id, display_order=index)

    async def _commit_session(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def _rollback_session(self) -> None:
        if self._session is not None:
            await self._session.rollback()
