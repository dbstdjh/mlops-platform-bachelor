CREATE TABLE "user" (
  "id" UUID,
  "email" STRING,
  "hashed_password" STRING,
  "is_active" BOOLEAN,
  "is_superuser" BOOLEAN,
  "is_verified" BOOLEAN,
  "created_at" TIMESTAMP,
  PRIMARY KEY ("id")
);

CREATE TABLE "api_key" (
  "id" UUID,
  "user_id" UUID,
  "name" STRING,
  "prefix" STRING,
  "hashed_key" STRING,
  "is_revoked" BOOLEAN (FALSE),
  "created_at" TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_api_key_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id")
);

CREATE TABLE "experiment" (
  "user_id" UUID,
  "id" UUID,
  "resource_id" UUID,
  "name" STRING,
  "logged_data_template" ARRAY[STRING],
  "created_at" TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_experiment_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id")
);

CREATE TABLE "run" (
  "id" UUID,
  "resource_id" UUID,
  "experiment_id" UUID,
  "dataset_id" UUID, NULLABLE,
  "status_id" UUID,
  "created_at" TIMESTAMP,
  "ended_at" TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_run_experiment_id"
    FOREIGN KEY ("experiment_id")
      REFERENCES "experiment"("id")
);

CREATE TABLE "deployment" (
  "user_id" UUID,
  "id" UUID,
  "resource_id" UUID,
  "name" STRING,
  "input_schema" JSONB,
  "output_schema" JSONB,
  "status_id" UUID,
  "created_at" TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_deployment_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id")
);

CREATE TABLE "model_repository" (
  "user_id" UUID,
  "id" UUID,
  "resource_id" UUID,
  "name" STRING,
  "is_deleted" BOOLEAN,
  "created_at" TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_model_repository_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id")
);

CREATE TABLE "image_deployment" (
  "id" UUID,
  "image_tag" STRING,
  PRIMARY KEY ("id")
);

CREATE TABLE "file_deployment" (
  "id" UUID,
  "model_id" UUID,
  PRIMARY KEY ("id")
);

CREATE TABLE "resource" (
  "id" UUID,
  "labels" JSONB,
  PRIMARY KEY ("id")
);

CREATE TABLE "dataset" (
  "user_id" UUID,
  "id" UUID,
  "resource_id" UUID,
  "name" STRING,
  "s3_uri" STRING,
  "status_id" UUID,
  "version" INTEGER,
  "created_at" TIMESTAMP,
  "file_type" STRING,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_dataset_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id")
);

CREATE TABLE "run_step" (
  "run_id" UUID,
  "run_step_id" UUID,
  "logged_data" JSONB,
  "step" INTEGER,
  "timestamp" TIMESTAMP,
  PRIMARY KEY ("run_id", "run_step_id"),
  CONSTRAINT "FK_run_step_run_id"
    FOREIGN KEY ("run_id")
      REFERENCES "run"("id")
);

CREATE TABLE "feature" (
  "id" UUID,
  "name" STRING,
  "description" STRING,
  "is_globally_enabled" BOOLEAN,
  PRIMARY KEY ("id")
);

CREATE TABLE "user_feature_config" (
  "feature_id" UUID,
  "user_id" UUID,
  "is_active" BOOLEAN,
  "config_data" JSONB,
  PRIMARY KEY ("feature_id", "user_id"),
  CONSTRAINT "FK_user_feature_config_feature_id"
    FOREIGN KEY ("feature_id")
      REFERENCES "feature"("id"),
  CONSTRAINT "FK_user_feature_config_user_id"
    FOREIGN KEY ("user_id")
      REFERENCES "user"("id")
);

CREATE TABLE "inference_log" (
  "deployment_id" UUID,
  "id" UUID,
  "timestamp" TIMESTAMP,
  "input_data" JSONB,
  "output_data" JSONB,
  "status_code" INTEGER,
  "latency_ms" DOUBLE,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_inference_log_deployment_id"
    FOREIGN KEY ("deployment_id")
      REFERENCES "deployment"("id")
);

CREATE TABLE "run_status" (
  "id" UUID,
  "name" STRING,
  PRIMARY KEY ("id")
);

CREATE TABLE "dashboard" (
  "id" UUID,
  "name" STRING,
  "grafana_uid" STRING UNIQUE,
  "is_system_locked" BOOLEAN,
  "created_at" TIMESTAMP,
  PRIMARY KEY ("id")
);

CREATE TABLE "run_dashboard" (
  "id" UUID,
  "run_id" UUID,
  PRIMARY KEY ("id")
);

CREATE TABLE "deployment_dashboard" (
  "id" UUID,
  "deployment_id" UUID,
  PRIMARY KEY ("id")
);

CREATE TABLE "model" (
  "id" UUID,
  "resource_id" UUID,
  "repository_id" UUID,
  "run_id" UUID, UNIQUE,
  "name" STRING,
  "version" STRING,
  "is_deleted" BOOLEAN,
  "s3_uri" STRING,
  "created_at" TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_model_repository_id"
    FOREIGN KEY ("repository_id")
      REFERENCES "model_repository"("id")
);

CREATE TABLE "dataset_status" (
  "id" UUID,
  "name" STRING,
  PRIMARY KEY ("id")
);

CREATE TABLE "deployment_status" (
  "id" UUID,
  "name" STRING,
  PRIMARY KEY ("id")
);

CREATE TABLE "deployment_task" (
  "id" UUID,
  "deployment_id" UUID,
  "type" STRING,
  "status" STRING,
  "created_at" TIMESTAMP,
  "claimed_at" TIMESTAMP,
  "completed_at" TIMESTAMP,
  "error_message" STRING,
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_deployment_task_deployment_id"
    FOREIGN KEY ("deployment_id")
      REFERENCES "deployment"("id")
);

