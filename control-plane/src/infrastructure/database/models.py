"""
SQLAlchemy ORM models — Infrastructure layer.

These map directly to the tables defined in data-model.sql.
Any schema change must be made in data-model.sql first, then reflected here.
"""

import uuid
from datetime import datetime, timezone

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import (
    Column, String, Boolean, Integer, Float, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from src.infrastructure.database.session import Base


# ===================== Lookup / Enum Tables ==================

class RunStatusORM(Base):
    __tablename__ = "run_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)


class DatasetStatusORM(Base):
    __tablename__ = "dataset_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)


class ModelStatusORM(Base):
    __tablename__ = "model_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)


class FileTypeORM(Base):
    __tablename__ = "file_type"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)


class DeploymentStatusORM(Base):
    __tablename__ = "deployment_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)


# ===================== Core Identity =========================

class UserORM(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "user"

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ApiKeyORM(Base):
    __tablename__ = "api_key"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="UQ_api_key_user_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    prefix = Column(String, nullable=False)
    hashed_key = Column(String, nullable=False)
    is_revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# ===================== Resource Metadata =====================

class ResourceORM(Base):
    __tablename__ = "resource"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    labels = Column(JSONB, nullable=False, default=dict)


# ===================== Feature Flags =========================

class FeatureORM(Base):
    __tablename__ = "feature"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    is_globally_enabled = Column(Boolean, nullable=False, default=True)


class UserFeatureConfigORM(Base):
    __tablename__ = "user_feature_config"

    feature_id = Column(UUID(as_uuid=True), ForeignKey("feature.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    is_active = Column(Boolean, nullable=False, default=True)
    config_data = Column(JSONB, nullable=False, default=dict)


# ===================== Experiment Tracking ===================

class ExperimentORM(Base):
    __tablename__ = "experiment"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="UQ_experiment_user_name"),
        UniqueConstraint("user_id", "slug", name="UQ_experiment_user_slug"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resource.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    logged_data_template = Column(ARRAY(String), default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DatasetORM(Base):
    __tablename__ = "dataset"
    __table_args__ = (
        UniqueConstraint("user_id", "name", "version", name="UQ_dataset_user_name_version"),
        UniqueConstraint("user_id", "slug", "version", name="UQ_dataset_user_slug_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resource.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    s3_uri = Column(String, nullable=True)
    status_id = Column(UUID(as_uuid=True), ForeignKey("dataset_status.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    file_type = Column(String, nullable=True)


class RunORM(Base):
    __tablename__ = "run"
    __table_args__ = (
        UniqueConstraint("experiment_id", "number", name="UQ_run_experiment_number"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resource.id", ondelete="CASCADE"), nullable=False)
    experiment_id = Column(UUID(as_uuid=True), ForeignKey("experiment.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("dataset.id", ondelete="SET NULL"), nullable=True)
    number = Column(Integer, nullable=False)
    status_id = Column(UUID(as_uuid=True), ForeignKey("run_status.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)


class RunStepORM(Base):
    __tablename__ = "run_step"
    __table_args__ = (
        UniqueConstraint("run_id", "step", name="UQ_run_step_run_id_step"),
    )

    run_id = Column(UUID(as_uuid=True), ForeignKey("run.id", ondelete="CASCADE"), primary_key=True)
    run_step_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    logged_data = Column(JSONB, nullable=False)
    step = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# ===================== Model Versioning & Registry ===========

class ModelRepositoryORM(Base):
    __tablename__ = "model_repository"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="UQ_model_repository_user_name"),
        UniqueConstraint("user_id", "slug", name="UQ_model_repository_user_slug"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resource.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ModelORM(Base):
    __tablename__ = "model"
    __table_args__ = (
        UniqueConstraint("repository_id", "version", name="UQ_model_repo_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resource.id", ondelete="CASCADE"), nullable=False)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("model_repository.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(UUID(as_uuid=True), ForeignKey("run.id", ondelete="SET NULL"), unique=True, nullable=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    s3_uri = Column(String, nullable=True)
    status_id = Column(UUID(as_uuid=True), ForeignKey("model_status.id"), nullable=False)
    file_type_id = Column(UUID(as_uuid=True), ForeignKey("file_type.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# ===================== Observability & Dashboards =============

class DashboardORM(Base):
    __tablename__ = "dashboard"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False, default="RUN_PLOT")
    grafana_uid = Column(String, unique=True, nullable=True)
    is_system_locked = Column(Boolean, nullable=False, default=False)
    config_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class RunDashboardORM(Base):
    __tablename__ = "run_dashboard"

    id = Column(UUID(as_uuid=True), ForeignKey("dashboard.id", ondelete="CASCADE"), primary_key=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("run.id", ondelete="CASCADE"), nullable=False)
    display_order = Column(Integer, nullable=False, default=0)


class DeploymentDashboardORM(Base):
    __tablename__ = "deployment_dashboard"

    id = Column(UUID(as_uuid=True), ForeignKey("dashboard.id", ondelete="CASCADE"), primary_key=True)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployment.id", ondelete="CASCADE"), nullable=False)


class InferenceLogORM(Base):
    __tablename__ = "inference_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployment.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    input_data = Column(JSONB, nullable=True)
    output_data = Column(JSONB, nullable=True)
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)


# ===================== Deployment (Phase 2) ===================

class DeploymentORM(Base):
    __tablename__ = "deployment"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="UQ_deployment_user_name"),
        UniqueConstraint("user_id", "slug", name="UQ_deployment_user_slug"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resource.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    input_schema = Column(JSONB, nullable=True)
    output_schema = Column(JSONB, nullable=True)
    endpoint_url = Column(String, nullable=True)
    k8s_namespace = Column(String, nullable=True)
    k8s_deployment_name = Column(String, nullable=True)
    k8s_service_name = Column(String, nullable=True)
    k8s_service_port = Column(Integer, nullable=True)
    status_id = Column(UUID(as_uuid=True), ForeignKey("deployment_status.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ImageDeploymentORM(Base):
    __tablename__ = "image_deployment"

    id = Column(UUID(as_uuid=True), ForeignKey("deployment.id", ondelete="CASCADE"), primary_key=True)
    image_tag = Column(String, nullable=False)


class FileDeploymentORM(Base):
    __tablename__ = "file_deployment"

    id = Column(UUID(as_uuid=True), ForeignKey("deployment.id", ondelete="CASCADE"), primary_key=True)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model.id", ondelete="RESTRICT"), nullable=False)


class DeploymentTaskORM(Base):
    __tablename__ = "deployment_task"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployment.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)
