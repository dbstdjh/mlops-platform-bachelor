# Phase 1 Pre-Kube Implementation Review

Here is a summary of the progress made in establishing the Phase 1 infrastructure and Control Plane scaffolding.

## 1. Infrastructure (Docker Compose)
- **Services Running:** PostgreSQL, MinIO, Gitea, and Grafana are fully operational.
- **MinIO Webhooks:** Configured an initialization container (`minio-init`) to automatically create the `datasets` and `models` buckets and register a webhook to the Control Plane for the `datasets` bucket.
- **Port Mapping Fixes:** Adjusted host ports to avoid local conflicts: PostgreSQL to `5433`, Gitea SSH to `2223`, and Gitea Web to `3002`.

## 2. Control Plane Scaffolding
- **Environment & Tooling:** Initialized the FastAPI application managed by `uv`.
- **Configuration:** Set up `pydantic-settings` to manage environment variables with local development defaults matching the docker-compose stack.
- **Database Schema:** Created SQLAlchemy ORM models that strictly reflect the `data-model.sql` definitions. Resolved `datetime` timezone awareness issues and deprecated `utcnow()` usages.
- **Public Identity Model:** Reworked the current Phase 1 dataset and model-registry surfaces so public APIs no longer expose internal UUID primary keys. Added immutable, server-generated `slug` fields for `dataset` and `model_repository`, with uniqueness scoped per user.
- **Dev User Seeding:** Implemented a startup script to automatically seed a "dev" user to satisfy Foreign Key constraints for early development before the IAM module is built.

## 3. Strict Onion Architecture Implementation
- **Core Entities:** Implemented pure domain models for `Resource`, `ModelRepository`, `Model`, and `Dataset`.
- **Core Ports:** Defined repository interfaces (`ResourceRepository`, `ModelRepositoryRepo`, etc.) and a `StoragePort`.
- **Infrastructure Adapters:** Built SQLAlchemy repository implementations and a MinIO storage adapter.
- **Dependency Injection:** Moved MinIO client construction into the FastAPI dependency layer so external clients are injected rather than initialized inside business-facing classes.
- **Application Services:** Created `DatasetService` and `ModelRegistryService` handling business logic, slug generation, pre-signed URLs, and webhook confirmations without touching infrastructure directly.
- **Presentation Layer:** Set up API routers (`/datasets` and `/repositories`) and wired dependencies via FastAPI's `Depends` DI mechanism.

## 4. API Endpoints Working End-to-End
- **Health Check:** Validated database connection.
- **Model Registry:**
  - `POST /api/v1/repositories` (Create)
  - `GET /api/v1/repositories` (List)
  - `GET /api/v1/repositories/{repository_slug}` (Get)
  - `DELETE /api/v1/repositories/{repository_slug}` (Soft Delete)
  - `POST /api/v1/repositories/{repository_slug}/models` (Create Version)
  - `GET /api/v1/repositories/{repository_slug}/models` (List Versions)
  - `GET /api/v1/repositories/{repository_slug}/models/{version}` (Get Version)
  - `POST /api/v1/repositories/{repository_slug}/models/{version}:upload` (Pre-signed URL generation for models bucket)
- **Feature Registry:**
  - `POST /api/v1/datasets:upload` (Creates PENDING dataset version, resolves or creates immutable slug, returns pre-signed URL)
  - `POST /api/v1/datasets:confirm_upload` (Webhook confirmation for dataset uploads)
  - `GET /api/v1/datasets` (List)
  - `GET /api/v1/datasets/{dataset_slug}/versions/{version}` (Get Version)
  - `GET /api/v1/datasets/{dataset_slug}:download` (Latest READY version)
  - `GET /api/v1/datasets/{dataset_slug}/versions/{version}:download` (Specific READY version)

## 5. Testing
- **Unit Coverage:** Added unit tests for entities, slug generation, dependency wiring, MinIO adapter behavior, application services, and route handlers.
- **Integration Coverage:** Wrote API integration tests for the dataset and model-registry flows, including upload URL generation, slug-based lookups, dataset confirmation, and downloads.
- **E2E Coverage:** Added a Phase 1 registry smoke journey covering repository creation, model version creation, upload URL generation, dataset upload initiation, webhook confirmation, and download retrieval.
- **Test Isolation:** Moved integration and E2E suites onto isolated throwaway PostgreSQL databases so the default development database is not polluted during test runs.
- **Compatibility Fixes:** Discovered and fixed async fixture compatibility issues with `pytest-asyncio`.

The current `make test` flow passes with unit, integration, and E2E coverage for the implemented Phase 1 scaffolding.
