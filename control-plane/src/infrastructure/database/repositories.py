"""
Infrastructure adapters: SQLAlchemy repository implementations.

These implement the core ports (interfaces) defined in src/core/ports/repositories.py.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.entities.api_key import ApiKey
from src.core.entities.dashboard import Dashboard, RunDashboardRecord
from src.core.entities.dataset import Dataset
from src.core.entities.experiment_tracking import Experiment, Run, RunStep
from src.core.entities.model import Model
from src.core.entities.model_repository import ModelRepository
from src.core.entities.resource import Resource
from src.core.ports.repositories import (
    ApiKeyRepo,
    DashboardRepo,
    DatasetRepo,
    ExperimentRepo,
    ModelRepo,
    ModelRepositoryRepo,
    ResourceRepository,
    RunRepo,
    RunStepRepo,
)
from src.infrastructure.database.models import (
    ApiKeyORM,
    DashboardORM,
    DatasetORM,
    DatasetStatusORM,
    ExperimentORM,
    FileTypeORM,
    ModelORM,
    ModelRepositoryORM,
    ModelStatusORM,
    ResourceORM,
    RunORM,
    RunDashboardORM,
    RunStatusORM,
    RunStepORM,
)


class SqlAlchemyApiKeyRepo(ApiKeyRepo):
    """SQLAlchemy adapter for API key persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, api_key: ApiKey) -> ApiKey:
        orm = ApiKeyORM(
            id=api_key.id,
            user_id=api_key.user_id,
            name=api_key.name,
            prefix=api_key.prefix,
            hashed_key=api_key.hashed_key,
            is_revoked=api_key.is_revoked,
            created_at=api_key.created_at,
        )
        self._session.add(orm)
        await self._session.flush()
        return api_key

    async def list_by_user(self, user_id: uuid.UUID) -> list[ApiKey]:
        stmt = (
            select(ApiKeyORM)
            .where(ApiKeyORM.user_id == user_id)
            .order_by(ApiKeyORM.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(orm) for orm in result.scalars().all()]

    async def get_by_prefix(self, prefix: str) -> Optional[ApiKey]:
        stmt = select(ApiKeyORM).where(ApiKeyORM.prefix == prefix)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return self._to_entity(orm)

    async def prefix_exists(self, prefix: str) -> bool:
        stmt = select(ApiKeyORM.id).where(ApiKeyORM.prefix == prefix)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def name_exists(self, user_id: uuid.UUID, name: str) -> bool:
        stmt = select(ApiKeyORM.id).where(
            ApiKeyORM.user_id == user_id,
            ApiKeyORM.name == name,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def revoke(self, user_id: uuid.UUID, name: str) -> bool:
        stmt = select(ApiKeyORM).where(
            ApiKeyORM.user_id == user_id,
            ApiKeyORM.name == name,
            ApiKeyORM.is_revoked == False,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return False
        orm.is_revoked = True
        await self._session.flush()
        return True

    def _to_entity(self, orm: ApiKeyORM) -> ApiKey:
        return ApiKey(
            id=orm.id,
            user_id=orm.user_id,
            name=orm.name,
            prefix=orm.prefix,
            hashed_key=orm.hashed_key,
            is_revoked=orm.is_revoked,
            created_at=orm.created_at,
        )


class SqlAlchemyDashboardRepo(DashboardRepo):
    """SQLAlchemy adapter for saved run dashboard persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_run_dashboard(
        self,
        dashboard: Dashboard,
        *,
        run_id: uuid.UUID,
        display_order: int,
    ) -> RunDashboardRecord:
        dashboard_orm = DashboardORM(
            id=dashboard.id,
            name=dashboard.name,
            kind=dashboard.kind,
            grafana_uid=dashboard.grafana_uid,
            is_system_locked=dashboard.is_system_locked,
            config_data=dashboard.config_data,
            created_at=dashboard.created_at,
        )
        run_dashboard_orm = RunDashboardORM(id=dashboard.id, run_id=run_id, display_order=display_order)
        self._session.add(dashboard_orm)
        self._session.add(run_dashboard_orm)
        await self._session.flush()
        return self._to_record(dashboard_orm, run_dashboard_orm)

    async def list_by_run(self, run_id: uuid.UUID) -> list[RunDashboardRecord]:
        stmt = (
            select(DashboardORM, RunDashboardORM)
            .join(RunDashboardORM, RunDashboardORM.id == DashboardORM.id)
            .where(RunDashboardORM.run_id == run_id)
            .order_by(RunDashboardORM.display_order.asc(), DashboardORM.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_record(dashboard, run_dashboard) for dashboard, run_dashboard in result.all()]

    async def get_by_id_for_run(self, run_id: uuid.UUID, dashboard_id: uuid.UUID) -> Optional[RunDashboardRecord]:
        stmt = (
            select(DashboardORM, RunDashboardORM)
            .join(RunDashboardORM, RunDashboardORM.id == DashboardORM.id)
            .where(RunDashboardORM.run_id == run_id, RunDashboardORM.id == dashboard_id)
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()
        if not row:
            return None
        return self._to_record(row[0], row[1])

    async def update_run_dashboard(
        self,
        run_id: uuid.UUID,
        dashboard_id: uuid.UUID,
        *,
        name: str | None = None,
        grafana_uid: str | None = None,
        config_data: dict | None = None,
        display_order: int | None = None,
    ) -> Optional[RunDashboardRecord]:
        row = await self._get_row(run_id, dashboard_id)
        if not row:
            return None
        dashboard_orm, run_dashboard_orm = row
        if name is not None:
            dashboard_orm.name = name
        if grafana_uid is not None:
            dashboard_orm.grafana_uid = grafana_uid
        if config_data is not None:
            dashboard_orm.config_data = config_data
        if display_order is not None:
            run_dashboard_orm.display_order = display_order
        await self._session.flush()
        return self._to_record(dashboard_orm, run_dashboard_orm)

    async def delete_run_dashboard(self, run_id: uuid.UUID, dashboard_id: uuid.UUID) -> bool:
        row = await self._get_row(run_id, dashboard_id)
        if not row:
            return False
        dashboard_orm, _run_dashboard_orm = row
        await self._session.delete(dashboard_orm)
        await self._session.flush()
        return True

    async def _get_row(self, run_id: uuid.UUID, dashboard_id: uuid.UUID) -> tuple[DashboardORM, RunDashboardORM] | None:
        stmt = (
            select(DashboardORM, RunDashboardORM)
            .join(RunDashboardORM, RunDashboardORM.id == DashboardORM.id)
            .where(RunDashboardORM.run_id == run_id, RunDashboardORM.id == dashboard_id)
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()
        if not row:
            return None
        return row[0], row[1]

    def _to_record(self, dashboard_orm: DashboardORM, run_dashboard_orm: RunDashboardORM) -> RunDashboardRecord:
        config_data = dashboard_orm.config_data or {}
        metrics = [str(metric) for metric in config_data.get("metrics", [])]
        return RunDashboardRecord(
            id=dashboard_orm.id,
            run_id=run_dashboard_orm.run_id,
            title=dashboard_orm.name,
            plot_type=str(config_data.get("plot_type", "line")),
            metrics=metrics,
            display_order=run_dashboard_orm.display_order,
            grafana_uid=dashboard_orm.grafana_uid,
            created_at=dashboard_orm.created_at,
        )


class SqlAlchemyResourceRepository(ResourceRepository):
    """SQLAlchemy adapter for resource (metadata) persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, resource: Resource) -> Resource:
        orm = ResourceORM(id=resource.id, labels=resource.labels)
        self._session.add(orm)
        await self._session.flush()
        return resource

    async def get_by_id(self, resource_id: uuid.UUID) -> Optional[Resource]:
        result = await self._session.get(ResourceORM, resource_id)
        if not result:
            return None
        return Resource(id=result.id, labels=result.labels)

    async def update_labels(self, resource_id: uuid.UUID, labels: dict) -> Optional[Resource]:
        orm = await self._session.get(ResourceORM, resource_id)
        if not orm:
            return None
        orm.labels = labels
        await self._session.flush()
        return Resource(id=orm.id, labels=orm.labels)


class SqlAlchemyModelRepositoryRepo(ModelRepositoryRepo):
    """SQLAlchemy adapter for model repository persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, repo: ModelRepository) -> ModelRepository:
        orm = ModelRepositoryORM(
            id=repo.id,
            user_id=repo.user_id,
            resource_id=repo.resource_id,
            name=repo.name,
            slug=repo.slug,
            is_deleted=repo.is_deleted,
            created_at=repo.created_at,
        )
        self._session.add(orm)
        await self._session.flush()
        return repo

    async def get_by_slug(self, user_id: uuid.UUID, slug: str) -> Optional[ModelRepository]:
        stmt = select(ModelRepositoryORM).where(
            ModelRepositoryORM.user_id == user_id,
            ModelRepositoryORM.slug == slug,
            ModelRepositoryORM.is_deleted == False,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return ModelRepository(
            id=orm.id,
            user_id=orm.user_id,
            resource_id=orm.resource_id,
            name=orm.name,
            slug=orm.slug,
            is_deleted=orm.is_deleted,
            created_at=orm.created_at,
        )

    async def get_by_id(self, repository_id: uuid.UUID) -> Optional[ModelRepository]:
        orm = await self._session.get(ModelRepositoryORM, repository_id)
        if not orm or orm.is_deleted:
            return None
        return ModelRepository(
            id=orm.id,
            user_id=orm.user_id,
            resource_id=orm.resource_id,
            name=orm.name,
            slug=orm.slug,
            is_deleted=orm.is_deleted,
            created_at=orm.created_at,
        )

    async def list_by_user(self, user_id: uuid.UUID) -> list[ModelRepository]:
        stmt = select(ModelRepositoryORM).where(
            ModelRepositoryORM.user_id == user_id,
            ModelRepositoryORM.is_deleted == False,
        )
        result = await self._session.execute(stmt)
        return [
            ModelRepository(
                id=orm.id,
                user_id=orm.user_id,
                resource_id=orm.resource_id,
                name=orm.name,
                slug=orm.slug,
                is_deleted=orm.is_deleted,
                created_at=orm.created_at,
            )
            for orm in result.scalars().all()
        ]

    async def soft_delete(self, user_id: uuid.UUID, slug: str) -> bool:
        stmt = select(ModelRepositoryORM).where(
            ModelRepositoryORM.user_id == user_id,
            ModelRepositoryORM.slug == slug,
            ModelRepositoryORM.is_deleted == False,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return False
        orm.is_deleted = True
        await self._session.flush()
        return True

    async def slug_exists(self, user_id: uuid.UUID, slug: str) -> bool:
        stmt = select(ModelRepositoryORM.id).where(
            ModelRepositoryORM.user_id == user_id,
            ModelRepositoryORM.slug == slug,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None


class SqlAlchemyModelRepo(ModelRepo):
    """SQLAlchemy adapter for model (versioned artifact) persistence."""

    MODEL_FILE_TYPES = {"pickle", "undefined"}

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_status_id(self, name: str) -> uuid.UUID:
        stmt = select(ModelStatusORM.id).where(ModelStatusORM.name == name)
        result = await self._session.execute(stmt)
        status_id = result.scalar_one_or_none()
        if status_id:
            return status_id

        insert_stmt = (
            insert(ModelStatusORM)
            .values(id=uuid.uuid4(), name=name)
            .on_conflict_do_nothing(index_elements=[ModelStatusORM.name])
        )
        await self._session.execute(insert_stmt)
        await self._session.flush()
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def _get_file_type_id(self, name: str) -> uuid.UUID:
        if name not in self.MODEL_FILE_TYPES:
            raise ValueError(f"Unsupported model file type '{name}'")

        stmt = select(FileTypeORM.id).where(FileTypeORM.name == name)
        result = await self._session.execute(stmt)
        file_type_id = result.scalar_one_or_none()
        if file_type_id:
            return file_type_id

        insert_stmt = (
            insert(FileTypeORM)
            .values(id=uuid.uuid4(), name=name)
            .on_conflict_do_nothing(index_elements=[FileTypeORM.name])
        )
        await self._session.execute(insert_stmt)
        await self._session.flush()
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def create(self, model: Model) -> Model:
        status_id = await self._get_status_id(model.status)
        file_type_id = await self._get_file_type_id(model.file_type)
        orm = ModelORM(
            id=model.id,
            resource_id=model.resource_id,
            repository_id=model.repository_id,
            run_id=model.run_id,
            name=model.name,
            version=model.version,
            is_deleted=model.is_deleted,
            s3_uri=model.s3_uri,
            status_id=status_id,
            file_type_id=file_type_id,
            created_at=model.created_at,
        )
        self._session.add(orm)
        await self._session.flush()
        return model

    async def get_by_version(self, repository_id: uuid.UUID, version: str) -> Optional[Model]:
        stmt = select(ModelORM).where(
            ModelORM.repository_id == repository_id,
            ModelORM.version == version,
            ModelORM.is_deleted == False,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._model_from_orm(orm)

    async def list_by_repository(self, repository_id: uuid.UUID) -> list[Model]:
        stmt = select(ModelORM).where(
            ModelORM.repository_id == repository_id,
            ModelORM.is_deleted == False,
        )
        result = await self._session.execute(stmt)
        models = []
        for orm in result.scalars().all():
            models.append(await self._model_from_orm(orm))
        return models

    async def update_s3_uri(self, model_id: uuid.UUID, s3_uri: str) -> Optional[Model]:
        orm = await self._session.get(ModelORM, model_id)
        if not orm:
            return None
        orm.s3_uri = s3_uri
        await self._session.flush()
        return await self._model_from_orm(orm)

    async def update_file_type(self, model_id: uuid.UUID, file_type: str) -> Optional[Model]:
        orm = await self._session.get(ModelORM, model_id)
        if not orm:
            return None
        orm.file_type_id = await self._get_file_type_id(file_type)
        await self._session.flush()
        return await self._model_from_orm(orm)

    async def get_by_s3_uri(self, s3_uri: str) -> Optional[Model]:
        stmt = select(ModelORM).where(
            ModelORM.s3_uri == s3_uri,
            ModelORM.is_deleted == False,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._model_from_orm(orm)

    async def get_ready_by_version(self, repository_id: uuid.UUID, version: str) -> Optional[Model]:
        ready_status_id = await self._get_status_id("READY")
        stmt = select(ModelORM).where(
            ModelORM.repository_id == repository_id,
            ModelORM.version == version,
            ModelORM.is_deleted == False,
            ModelORM.status_id == ready_status_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._model_from_orm(orm)

    async def mark_ready(self, model_id: uuid.UUID) -> Optional[Model]:
        orm = await self._session.get(ModelORM, model_id)
        if not orm:
            return None
        ready_status_id = await self._get_status_id("READY")
        orm.status_id = ready_status_id
        await self._session.flush()
        return await self._model_from_orm(orm)

    async def get_by_run_id(self, run_id: uuid.UUID) -> Optional[Model]:
        stmt = select(ModelORM).where(
            ModelORM.run_id == run_id,
            ModelORM.is_deleted == False,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._model_from_orm(orm)

    async def _model_from_orm(self, orm: ModelORM) -> Model:
        status_stmt = select(ModelStatusORM).where(ModelStatusORM.id == orm.status_id)
        status_result = await self._session.execute(status_stmt)
        status = status_result.scalar_one()
        file_type_stmt = select(FileTypeORM).where(FileTypeORM.id == orm.file_type_id)
        file_type_result = await self._session.execute(file_type_stmt)
        file_type = file_type_result.scalar_one()
        return Model(
            id=orm.id,
            resource_id=orm.resource_id,
            repository_id=orm.repository_id,
            run_id=orm.run_id,
            name=orm.name,
            version=orm.version,
            is_deleted=orm.is_deleted,
            s3_uri=orm.s3_uri,
            status=status.name,
            file_type=file_type.name,
            created_at=orm.created_at,
        )


class SqlAlchemyExperimentRepo(ExperimentRepo):
    """SQLAlchemy adapter for experiment persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, experiment: Experiment) -> Experiment:
        orm = ExperimentORM(
            id=experiment.id,
            user_id=experiment.user_id,
            resource_id=experiment.resource_id,
            name=experiment.name,
            slug=experiment.slug,
            logged_data_template=experiment.logged_data_template,
            created_at=experiment.created_at,
        )
        self._session.add(orm)
        await self._session.flush()
        return experiment

    async def get_by_slug(self, user_id: uuid.UUID, slug: str) -> Optional[Experiment]:
        stmt = select(ExperimentORM).where(
            ExperimentORM.user_id == user_id,
            ExperimentORM.slug == slug,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return self._to_entity(orm)

    async def get_by_id(self, experiment_id: uuid.UUID) -> Optional[Experiment]:
        orm = await self._session.get(ExperimentORM, experiment_id)
        if not orm:
            return None
        return self._to_entity(orm)

    async def list_by_user(self, user_id: uuid.UUID) -> list[Experiment]:
        stmt = select(ExperimentORM).where(ExperimentORM.user_id == user_id).order_by(ExperimentORM.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_entity(orm) for orm in result.scalars().all()]

    async def slug_exists(self, user_id: uuid.UUID, slug: str) -> bool:
        stmt = select(ExperimentORM.id).where(
            ExperimentORM.user_id == user_id,
            ExperimentORM.slug == slug,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    def _to_entity(self, orm: ExperimentORM) -> Experiment:
        return Experiment(
            id=orm.id,
            user_id=orm.user_id,
            resource_id=orm.resource_id,
            name=orm.name,
            slug=orm.slug,
            logged_data_template=list(orm.logged_data_template or []),
            created_at=orm.created_at,
        )


class SqlAlchemyRunRepo(RunRepo):
    """SQLAlchemy adapter for run persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_status_id(self, name: str) -> uuid.UUID:
        stmt = select(RunStatusORM.id).where(RunStatusORM.name == name)
        result = await self._session.execute(stmt)
        status_id = result.scalar_one_or_none()
        if status_id:
            return status_id

        insert_stmt = (
            insert(RunStatusORM)
            .values(id=uuid.uuid4(), name=name)
            .on_conflict_do_nothing(index_elements=[RunStatusORM.name])
        )
        await self._session.execute(insert_stmt)
        await self._session.flush()
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def create(self, run: Run) -> Run:
        status_id = await self._get_status_id(run.status)
        orm = RunORM(
            id=run.id,
            resource_id=run.resource_id,
            experiment_id=run.experiment_id,
            dataset_id=run.dataset_id,
            number=run.number,
            status_id=status_id,
            created_at=run.created_at,
            ended_at=run.ended_at,
        )
        self._session.add(orm)
        await self._session.flush()
        return run

    async def get_by_number(self, experiment_id: uuid.UUID, number: int) -> Optional[Run]:
        stmt = select(RunORM).where(
            RunORM.experiment_id == experiment_id,
            RunORM.number == number,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._to_entity(orm)

    async def get_by_id(self, run_id: uuid.UUID) -> Optional[Run]:
        orm = await self._session.get(RunORM, run_id)
        if not orm:
            return None
        return await self._to_entity(orm)

    async def list_by_experiment(self, experiment_id: uuid.UUID) -> list[Run]:
        stmt = select(RunORM).where(RunORM.experiment_id == experiment_id).order_by(RunORM.number.desc())
        result = await self._session.execute(stmt)
        runs = []
        for orm in result.scalars().all():
            runs.append(await self._to_entity(orm))
        return runs

    async def get_next_number(self, experiment_id: uuid.UUID) -> int:
        stmt = select(func.max(RunORM.number)).where(RunORM.experiment_id == experiment_id)
        result = await self._session.execute(stmt)
        max_number = result.scalar_one_or_none()
        return (max_number or 0) + 1

    async def update_status(self, run_id: uuid.UUID, status: str, ended_at: datetime | None = None) -> Optional[Run]:
        orm = await self._session.get(RunORM, run_id)
        if not orm:
            return None
        orm.status_id = await self._get_status_id(status)
        orm.ended_at = ended_at
        await self._session.flush()
        return await self._to_entity(orm)

    async def _to_entity(self, orm: RunORM) -> Run:
        status_stmt = select(RunStatusORM).where(RunStatusORM.id == orm.status_id)
        status_result = await self._session.execute(status_stmt)
        status = status_result.scalar_one()
        return Run(
            id=orm.id,
            resource_id=orm.resource_id,
            experiment_id=orm.experiment_id,
            dataset_id=orm.dataset_id,
            number=orm.number,
            status=status.name,
            created_at=orm.created_at,
            ended_at=orm.ended_at,
        )


class SqlAlchemyRunStepRepo(RunStepRepo):
    """SQLAlchemy adapter for run-step persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_batch(self, steps: list[RunStep]) -> None:
        if not steps:
            return
        stmt = insert(RunStepORM).values(
            [
                {
                    "run_id": step.run_id,
                    "run_step_id": step.run_step_id,
                    "logged_data": step.logged_data,
                    "step": step.step,
                    "timestamp": step.timestamp,
                }
                for step in steps
            ]
        )
        stmt = stmt.on_conflict_do_update(
            constraint="UQ_run_step_run_id_step",
            set_={
                "logged_data": stmt.excluded.logged_data,
                "timestamp": stmt.excluded.timestamp,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_latest_for_run(self, run_id: uuid.UUID) -> Optional[RunStep]:
        stmt = (
            select(RunStepORM)
            .where(RunStepORM.run_id == run_id)
            .order_by(RunStepORM.step.desc(), RunStepORM.timestamp.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return self._to_entity(orm)

    async def list_by_run(self, run_id: uuid.UUID) -> list[RunStep]:
        stmt = select(RunStepORM).where(RunStepORM.run_id == run_id).order_by(RunStepORM.step.asc())
        result = await self._session.execute(stmt)
        return [self._to_entity(orm) for orm in result.scalars().all()]

    def _to_entity(self, orm: RunStepORM) -> RunStep:
        return RunStep(
            run_id=orm.run_id,
            run_step_id=orm.run_step_id,
            step=orm.step,
            logged_data={key: float(value) for key, value in orm.logged_data.items()},
            timestamp=orm.timestamp,
        )


class SqlAlchemyDatasetRepo(DatasetRepo):
    """SQLAlchemy adapter for dataset persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_status_id(self, name: str) -> uuid.UUID:
        """Get or create a dataset status by name."""
        stmt = select(DatasetStatusORM.id).where(DatasetStatusORM.name == name)
        result = await self._session.execute(stmt)
        status_id = result.scalar_one_or_none()
        if status_id:
            return status_id

        insert_stmt = (
            insert(DatasetStatusORM)
            .values(id=uuid.uuid4(), name=name)
            .on_conflict_do_nothing(index_elements=[DatasetStatusORM.name])
        )
        await self._session.execute(insert_stmt)
        await self._session.flush()
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def create(self, dataset: Dataset) -> Dataset:
        status_id = await self._get_status_id(dataset.status)
        orm = DatasetORM(
            id=dataset.id,
            user_id=dataset.user_id,
            resource_id=dataset.resource_id,
            name=dataset.name,
            slug=dataset.slug,
            s3_uri=dataset.s3_uri,
            status_id=status_id,
            version=dataset.version,
            created_at=dataset.created_at,
            file_type=dataset.file_type,
        )
        self._session.add(orm)
        await self._session.flush()
        return dataset

    async def get_latest_by_name(self, name: str, user_id: uuid.UUID) -> Optional[Dataset]:
        stmt = (
            select(DatasetORM)
            .where(
                DatasetORM.user_id == user_id,
                DatasetORM.name == name,
            )
            .order_by(DatasetORM.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._dataset_from_orm(orm)

    async def get_by_id(self, dataset_id: uuid.UUID) -> Optional[Dataset]:
        orm = await self._session.get(DatasetORM, dataset_id)
        if not orm:
            return None
        return await self._dataset_from_orm(orm)

    async def get_by_slug_and_version(self, slug: str, user_id: uuid.UUID, version: int) -> Optional[Dataset]:
        stmt = select(DatasetORM).where(
            DatasetORM.user_id == user_id,
            DatasetORM.slug == slug,
            DatasetORM.version == version,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._dataset_from_orm(orm)

    async def get_latest_ready(self, slug: str, user_id: uuid.UUID) -> Optional[Dataset]:
        ready_status_id = await self._get_status_id("READY")
        stmt = (
            select(DatasetORM)
            .where(
                DatasetORM.slug == slug,
                DatasetORM.user_id == user_id,
                DatasetORM.status_id == ready_status_id,
            )
            .order_by(DatasetORM.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._dataset_from_orm(orm)

    async def get_ready_by_slug_and_version(self, slug: str, user_id: uuid.UUID, version: int) -> Optional[Dataset]:
        ready_status_id = await self._get_status_id("READY")
        stmt = select(DatasetORM).where(
            DatasetORM.slug == slug,
            DatasetORM.user_id == user_id,
            DatasetORM.version == version,
            DatasetORM.status_id == ready_status_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return await self._dataset_from_orm(orm)

    async def list_by_user(self, user_id: uuid.UUID) -> list[Dataset]:
        stmt = select(DatasetORM).where(DatasetORM.user_id == user_id).order_by(DatasetORM.created_at.desc())
        result = await self._session.execute(stmt)
        datasets = []
        for orm in result.scalars().all():
            datasets.append(await self._dataset_from_orm(orm))
        return datasets

    async def mark_ready(self, slug: str, user_id: uuid.UUID, version: int, s3_uri: str) -> Optional[Dataset]:
        stmt = select(DatasetORM).where(
            DatasetORM.slug == slug,
            DatasetORM.user_id == user_id,
            DatasetORM.version == version,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        ready_status_id = await self._get_status_id("READY")
        orm.status_id = ready_status_id
        orm.s3_uri = s3_uri
        await self._session.flush()
        return await self._dataset_from_orm(orm)

    async def get_next_version(self, slug: str, user_id: uuid.UUID) -> int:
        stmt = select(func.max(DatasetORM.version)).where(
            DatasetORM.slug == slug,
            DatasetORM.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        max_version = result.scalar_one_or_none()
        return (max_version or 0) + 1

    async def slug_exists(self, slug: str, user_id: uuid.UUID) -> bool:
        stmt = select(DatasetORM.id).where(
            DatasetORM.slug == slug,
            DatasetORM.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _dataset_from_orm(self, orm: DatasetORM) -> Dataset:
        status_stmt = select(DatasetStatusORM).where(DatasetStatusORM.id == orm.status_id)
        status_result = await self._session.execute(status_stmt)
        status = status_result.scalar_one()
        return Dataset(
            id=orm.id,
            user_id=orm.user_id,
            resource_id=orm.resource_id,
            name=orm.name,
            slug=orm.slug,
            s3_uri=orm.s3_uri,
            status=status.name,
            version=orm.version,
            created_at=orm.created_at,
            file_type=orm.file_type,
        )
