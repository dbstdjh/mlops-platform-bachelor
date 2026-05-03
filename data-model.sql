-- ============================================================
-- MLOps Platform Data Model
-- Source of truth for the database schema.
-- All changes to the schema MUST be reflected here first.
-- ============================================================

-- ===================== Lookup / Enum Tables ==================

CREATE TABLE "run_status" (
  "id" UUID NOT NULL,
  "name" VARCHAR NOT NULL UNIQUE,
  PRIMARY KEY ("id")
);

CREATE TABLE "dataset_status" (
  "id" UUID NOT NULL,
  "name" VARCHAR NOT NULL UNIQUE,
  PRIMARY KEY ("id")
);

CREATE TABLE "model_status" (
  "id" UUID NOT NULL,
  "name" VARCHAR NOT NULL UNIQUE,
  PRIMARY KEY ("id")
);

CREATE TABLE "file_type" (
  "id" UUID NOT NULL,
  "name" VARCHAR NOT NULL UNIQUE,
  PRIMARY KEY ("id")
);

CREATE TABLE "deployment_status" (
  "id" UUID NOT NULL,
  "name" VARCHAR NOT NULL UNIQUE,
  PRIMARY KEY ("id")
);

-- ===================== Core Identity =========================

CREATE TABLE "user" (
  "id" UUID NOT NULL,
  "email" VARCHAR NOT NULL UNIQUE,
  "hashed_password" VARCHAR NOT NULL,
  "is_active" BOOLEAN NOT NULL DEFAULT TRUE,
  "is_superuser" BOOLEAN NOT NULL DEFAULT FALSE,
  "is_verified" BOOLEAN NOT NULL DEFAULT FALSE,
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY ("id")
);

CREATE TABLE "api_key" (
  "id" UUID NOT NULL,
  "user_id" UUID NOT NULL,
  "name" VARCHAR NOT NULL,
  "prefix" VARCHAR NOT NULL,
  "hashed_key" VARCHAR NOT NULL,
  "is_revoked" BOOLEAN NOT NULL DEFAULT FALSE,
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY ("id"),
  CONSTRAINT "UQ_api_key_user_name"
    UNIQUE ("user_id", "name"),
  CONSTRAINT "FK_api_key_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id") ON DELETE CASCADE
);

-- ===================== Resource Metadata =====================

CREATE TABLE "resource" (
  "id" UUID NOT NULL,
  "labels" JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY ("id")
);

-- ===================== Feature Flags =========================

CREATE TABLE "feature" (
  "id" UUID NOT NULL,
  "name" VARCHAR NOT NULL UNIQUE,
  "description" VARCHAR,
  "is_globally_enabled" BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY ("id")
);

CREATE TABLE "user_feature_config" (
  "feature_id" UUID NOT NULL,
  "user_id" UUID NOT NULL,
  "is_active" BOOLEAN NOT NULL DEFAULT TRUE,
  "config_data" JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY ("feature_id", "user_id"),
  CONSTRAINT "FK_user_feature_config_feature_id"
    FOREIGN KEY ("feature_id")
      REFERENCES "feature"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_user_feature_config_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id") ON DELETE CASCADE
);

-- ===================== Experiment Tracking ===================

CREATE TABLE "experiment" (
  "id" UUID NOT NULL,
  "user_id" UUID NOT NULL,
  "resource_id" UUID NOT NULL,
  "name" VARCHAR NOT NULL,
  "slug" VARCHAR NOT NULL,
  "logged_data_template" VARCHAR[] DEFAULT '{}',
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_experiment_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_experiment_resource_id"
    FOREIGN KEY ("resource_id")
      REFERENCES "resource"("id") ON DELETE CASCADE,
  CONSTRAINT "UQ_experiment_user_name"
    UNIQUE ("user_id", "name"),
  CONSTRAINT "UQ_experiment_user_slug"
    UNIQUE ("user_id", "slug")
);

CREATE TABLE "dataset" (
  "id" UUID NOT NULL,
  "user_id" UUID NOT NULL,
  "resource_id" UUID NOT NULL,
  "name" VARCHAR NOT NULL,
  "slug" VARCHAR NOT NULL,
  "s3_uri" VARCHAR,
  "status_id" UUID NOT NULL,
  "version" INTEGER NOT NULL DEFAULT 1,
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  "file_type" VARCHAR,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_dataset_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_dataset_resource_id"
    FOREIGN KEY ("resource_id")
      REFERENCES "resource"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_dataset_status_id"
    FOREIGN KEY ("status_id")
      REFERENCES "dataset_status"("id"),
  CONSTRAINT "UQ_dataset_user_name_version"
    UNIQUE ("user_id", "name", "version"),
  CONSTRAINT "UQ_dataset_user_slug_version"
    UNIQUE ("user_id", "slug", "version")
);

CREATE TABLE "run" (
  "id" UUID NOT NULL,
  "resource_id" UUID NOT NULL,
  "experiment_id" UUID NOT NULL,
  "dataset_id" UUID,
  "number" INTEGER NOT NULL,
  "status_id" UUID NOT NULL,
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  "ended_at" TIMESTAMP WITH TIME ZONE,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_run_resource_id"
    FOREIGN KEY ("resource_id")
      REFERENCES "resource"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_run_experiment_id"
    FOREIGN KEY ("experiment_id")
      REFERENCES "experiment"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_run_dataset_id"
    FOREIGN KEY ("dataset_id")
      REFERENCES "dataset"("id") ON DELETE SET NULL,
  CONSTRAINT "FK_run_status_id"
    FOREIGN KEY ("status_id")
      REFERENCES "run_status"("id"),
  CONSTRAINT "UQ_run_experiment_number"
    UNIQUE ("experiment_id", "number")
);

CREATE TABLE "run_step" (
  "run_id" UUID NOT NULL,
  "run_step_id" UUID NOT NULL,
  "logged_data" JSONB NOT NULL,
  "step" INTEGER NOT NULL,
  "timestamp" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY ("run_id", "run_step_id"),
  CONSTRAINT "UQ_run_step_run_id_step"
    UNIQUE ("run_id", "step"),
  CONSTRAINT "FK_run_step_run_id"
    FOREIGN KEY ("run_id")
      REFERENCES "run"("id") ON DELETE CASCADE
);

-- ===================== Model Versioning & Registry ===========

CREATE TABLE "model_repository" (
  "id" UUID NOT NULL,
  "user_id" UUID NOT NULL,
  "resource_id" UUID NOT NULL,
  "name" VARCHAR NOT NULL,
  "slug" VARCHAR NOT NULL,
  "is_deleted" BOOLEAN NOT NULL DEFAULT FALSE,
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_model_repository_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_model_repository_resource_id"
    FOREIGN KEY ("resource_id")
      REFERENCES "resource"("id") ON DELETE CASCADE,
  CONSTRAINT "UQ_model_repository_user_name"
    UNIQUE ("user_id", "name"),
  CONSTRAINT "UQ_model_repository_user_slug"
    UNIQUE ("user_id", "slug")
);

CREATE TABLE "model" (
  "id" UUID NOT NULL,
  "resource_id" UUID NOT NULL,
  "repository_id" UUID NOT NULL,
  "run_id" UUID UNIQUE,
  "name" VARCHAR NOT NULL,
  "version" VARCHAR NOT NULL,
  "is_deleted" BOOLEAN NOT NULL DEFAULT FALSE,
  "s3_uri" VARCHAR,
  "status_id" UUID NOT NULL,
  "file_type_id" UUID NOT NULL,
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_model_resource_id"
    FOREIGN KEY ("resource_id")
      REFERENCES "resource"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_model_repository_id"
    FOREIGN KEY ("repository_id")
      REFERENCES "model_repository"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_model_run_id"
    FOREIGN KEY ("run_id")
      REFERENCES "run"("id") ON DELETE SET NULL,
  CONSTRAINT "FK_model_status_id"
    FOREIGN KEY ("status_id")
      REFERENCES "model_status"("id"),
  CONSTRAINT "FK_model_file_type_id"
    FOREIGN KEY ("file_type_id")
      REFERENCES "file_type"("id"),
  CONSTRAINT "UQ_model_repo_version"
    UNIQUE ("repository_id", "version")
);

-- ===================== Deployment (Phase 2) ===================

CREATE TABLE "deployment" (
  "id" UUID NOT NULL,
  "user_id" UUID NOT NULL,
  "resource_id" UUID NOT NULL,
  "name" VARCHAR NOT NULL,
  "slug" VARCHAR NOT NULL,
  "input_schema" JSONB,
  "output_schema" JSONB,
  "endpoint_url" VARCHAR,
  "k8s_namespace" VARCHAR,
  "k8s_deployment_name" VARCHAR,
  "k8s_service_name" VARCHAR,
  "k8s_service_port" INTEGER,
  "status_id" UUID NOT NULL,
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_deployment_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_deployment_resource_id"
    FOREIGN KEY ("resource_id")
      REFERENCES "resource"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_deployment_status_id"
    FOREIGN KEY ("status_id")
      REFERENCES "deployment_status"("id"),
  CONSTRAINT "UQ_deployment_user_name"
    UNIQUE ("user_id", "name"),
  CONSTRAINT "UQ_deployment_user_slug"
    UNIQUE ("user_id", "slug")
);

CREATE TABLE "image_deployment" (
  "id" UUID NOT NULL,
  "image_tag" VARCHAR NOT NULL,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_image_deployment_id"
    FOREIGN KEY ("id")
      REFERENCES "deployment"("id") ON DELETE CASCADE
);

CREATE TABLE "file_deployment" (
  "id" UUID NOT NULL,
  "model_id" UUID NOT NULL,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_file_deployment_id"
    FOREIGN KEY ("id")
      REFERENCES "deployment"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_file_deployment_model_id"
    FOREIGN KEY ("model_id")
      REFERENCES "model"("id") ON DELETE RESTRICT
);

CREATE TABLE "deployment_task" (
  "id" UUID NOT NULL,
  "deployment_id" UUID NOT NULL,
  "type" VARCHAR NOT NULL,
  "status" VARCHAR NOT NULL DEFAULT 'PENDING',
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  "claimed_at" TIMESTAMP WITH TIME ZONE,
  "completed_at" TIMESTAMP WITH TIME ZONE,
  "error_message" VARCHAR,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_deployment_task_deployment_id"
    FOREIGN KEY ("deployment_id")
      REFERENCES "deployment"("id") ON DELETE CASCADE
);

-- ===================== Observability & Dashboards =============

CREATE TABLE "dashboard" (
  "id" UUID NOT NULL,
  "name" VARCHAR NOT NULL,
  "kind" VARCHAR NOT NULL DEFAULT 'RUN_PLOT',
  "grafana_uid" VARCHAR UNIQUE,
  "is_system_locked" BOOLEAN NOT NULL DEFAULT FALSE,
  "config_data" JSONB NOT NULL DEFAULT '{}',
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY ("id")
);

CREATE TABLE "run_dashboard" (
  "id" UUID NOT NULL,
  "run_id" UUID NOT NULL,
  "display_order" INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_run_dashboard_id"
    FOREIGN KEY ("id")
      REFERENCES "dashboard"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_run_dashboard_run_id"
    FOREIGN KEY ("run_id")
      REFERENCES "run"("id") ON DELETE CASCADE
);

CREATE TABLE "deployment_dashboard" (
  "id" UUID NOT NULL,
  "deployment_id" UUID NOT NULL,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_deployment_dashboard_id"
    FOREIGN KEY ("id")
      REFERENCES "dashboard"("id") ON DELETE CASCADE,
  CONSTRAINT "FK_deployment_dashboard_deployment_id"
    FOREIGN KEY ("deployment_id")
      REFERENCES "deployment"("id") ON DELETE CASCADE
);

CREATE TABLE "inference_log" (
  "id" UUID NOT NULL,
  "deployment_id" UUID NOT NULL,
  "timestamp" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  "input_data" JSONB,
  "output_data" JSONB,
  "status_code" INTEGER,
  "latency_ms" DOUBLE PRECISION,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_inference_log_deployment_id"
    FOREIGN KEY ("deployment_id")
      REFERENCES "deployment"("id") ON DELETE CASCADE
);

-- ===================== Seed Data =============================

INSERT INTO "run_status" ("id", "name") VALUES
  (gen_random_uuid(), 'RUNNING'),
  (gen_random_uuid(), 'COMPLETED'),
  (gen_random_uuid(), 'FAILED')
ON CONFLICT ("name") DO NOTHING;

INSERT INTO "dataset_status" ("id", "name") VALUES
  (gen_random_uuid(), 'PENDING'),
  (gen_random_uuid(), 'READY')
ON CONFLICT ("name") DO NOTHING;

INSERT INTO "model_status" ("id", "name") VALUES
  (gen_random_uuid(), 'PENDING'),
  (gen_random_uuid(), 'READY')
ON CONFLICT ("name") DO NOTHING;

INSERT INTO "file_type" ("id", "name") VALUES
  (gen_random_uuid(), 'pickle'),
  (gen_random_uuid(), 'undefined')
ON CONFLICT ("name") DO NOTHING;

INSERT INTO "deployment_status" ("id", "name") VALUES
  (gen_random_uuid(), 'PENDING'),
  (gen_random_uuid(), 'DEPLOYING'),
  (gen_random_uuid(), 'ACTIVE'),
  (gen_random_uuid(), 'FAILED'),
  (gen_random_uuid(), 'DELETING'),
  (gen_random_uuid(), 'DELETED')
ON CONFLICT ("name") DO NOTHING;

INSERT INTO "feature" ("id", "name", "description", "is_globally_enabled") VALUES
  (
    gen_random_uuid(),
    'custom_deployments',
    'Allows users to manage custom Docker images in the Gitea artifact registry and deploy image tags.',
    TRUE
  )
ON CONFLICT ("name") DO NOTHING;

-- ===================== Deployment Eventing ====================

CREATE OR REPLACE FUNCTION notify_deployment_task()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('deployment_tasks', '');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER deployment_task_inserted
    AFTER INSERT ON deployment_task
    FOR EACH ROW
    EXECUTE FUNCTION notify_deployment_task();
