# CLAUDE.md — MLOps Platform Agent Instructions

> **Project Context: Bachelor's Thesis**
> This is a focused, high-quality Proof-of-Concept MLOps platform. Do not introduce enterprise-scale bloat, unnecessary microservices, or over-engineered abstractions. Write clean, robust, and intelligent code. Follow the established architectural patterns strictly.

## Development Phases

The project is split into two phases. **Always check which phase is currently active before starting work.**

### Phase 1: Pre-Kube (COMPLETED)

Phase 1 delivered the initial Control Plane, SDK, dashboard, storage, registry, and observability foundation. Docker Compose is no longer the local orchestration path.

**Completed scope:**
- Control Plane API: Users & IAM, Experiment Tracking, Model Versioning & Registry, Feature Registry, Observability, Artifact Registry
- Python SDK
- React Dashboard
- PostgreSQL, MinIO, Gitea, and Grafana infrastructure

### Phase 2: Post-Kube (CURRENT)

Phase 2 introduces Minikube/Kubernetes as the local platform runtime, followed by the Deployment Service, Edge Gateway, model containers, and the deployment module on the Control Plane.

**Current infrastructure baseline:**
- Kubernetes manifests live under `k8s/base/` and are managed with Kustomize.
- Local namespace: `mldlc`
- Local Ingress hosts: `dashboard.mldlc.local`, `api.mldlc.local`, `gateway.mldlc.local`, `minio.mldlc.local`, `console.minio.mldlc.local`, `gitea.mldlc.local`, `grafana.mldlc.local`
- Local Postgres is reachable through ingress-nginx TCP forwarding at `127.0.0.1:15432` when `minikube tunnel` is running.
- Use Minikube plus the ingress addon and `minikube tunnel` for local access.

## Documentation

**Read the docs before writing any code.** The `docs/` directory is the single source of truth for all architectural decisions. The documentation is structured as follows:

```
docs/
├── overview.md                              # Platform overview, components, core workflows
├── verification_criteria.md                 # Testing and verification requirements
├── architecture/
│   ├── system_design.md                     # Onion architecture, Edge Gateway pattern
│   └── security_and_iam.md                  # JWT, Per-Tenant Encrypted Service Principal
├── components/
│   ├── experiment_tracking.md               # Runs, experiments, model registry, zombie runs
│   ├── feature_registry.md                  # Dataset upload/download, pre-signed URLs, webhooks
│   ├── model_serving.md                     # Deployment architecture, Pydantic JSON Schema
│   ├── observability_and_grafana.md         # Grafana embedding, dashboard provisioning
│   └── edge_gateway.md                      # Go gateway: JWT, schema validation, logging
└── infrastructure/
    ├── overview.md                           # Infrastructure components, architectural workflows
    ├── minio_gitea_setup.md                  # MinIO buckets, webhooks, Gitea unified storage
    └── deployment_eventing.md               # PostgreSQL LISTEN/NOTIFY task queue pattern
```

Always cross-reference the `data-model.sql` file for the current database schema.

## Monorepo Structure

This is a monorepo. Each deployable service is an independent package:

```
/                           # Root
├── docs/                   # Architecture documentation
├── data-model.sql          # Database schema (source of truth)
├── control-plane/          # FastAPI backend (Python)
├── sdk/                    # Python SDK for data scientists
├── deployment-service/     # Event-driven deployment worker (Python)
├── edge-gateway/           # API Gateway (Go)
├── dashboard/              # React + Tailwind CSS web app
├── k8s/                    # Local Kubernetes manifests (Kustomize)
└── Makefile                # Build, test, and run automation
```

## Technology & Tooling

### Python Services (Control Plane, SDK, Deployment Service)

- **Package manager:** Use `uv` exclusively. Each Python package has its own independent `uv` environment with its own `pyproject.toml`. Do NOT use pip, poetry, or conda.
  - `control-plane/` has its own `uv` project
  - `sdk/` has its own `uv` project
  - `deployment-service/` has its own `uv` project
- **Framework:** FastAPI for the Control Plane.
- **ORM:** SQLAlchemy (async) for database interactions.
- **Validation:** Pydantic for all data contracts.
- **Architecture:** Strict onion architecture for the Control Plane (core → application → infrastructure → presentation). See `docs/architecture/system_design.md`.

### Go Service (Edge Gateway)

- Use Go modules (`go.mod`).
- JSON Schema validation via `github.com/santhosh-tekuri/jsonschema/v5` or equivalent.
- Standard `net/http` or a minimal router.

### Frontend (Dashboard)

- React + Tailwind CSS. Read-only observability dashboard.
- Minimal frontend processing — the backend structures data for easy rendering.

### Infrastructure

- **PostgreSQL:** Central database and message broker (LISTEN/NOTIFY).
- **MinIO:** S3-compatible object storage. Buckets: `datasets` and `models` with upload webhooks, plus Gitea storage buckets.
- **Gitea:** Artifact registry (Docker images) with unified MinIO storage backend.
- **Kubernetes (Minikube):** Local orchestration for platform services and model containers.
- **Grafana:** Embedded monitoring and plotting.

## Key Architectural Rules

1. **Server-side IDs only.** The client (SDK) never generates primary keys. All UUIDs are generated by the Control Plane.
2. **Pre-signed URLs for heavy data.** The Control Plane never handles dataset or model file bytes. Use MinIO pre-signed URLs exclusively. See `docs/components/feature_registry.md`.
3. **Event-driven deployments.** The Deployment Service is triggered via PostgreSQL `LISTEN/NOTIFY`, not polling. See `docs/infrastructure/deployment_eventing.md`.
4. **Strict state machines.** Runs follow `RUNNING → COMPLETED | FAILED`. Deployments follow `PENDING → DEPLOYING → ACTIVE | FAILED`. The SDK wraps training loops in try/catch to prevent zombie runs.
5. **Edge authentication.** JWT validation for model inference happens at the Go Gateway, not in the model containers.
6. **Resources have metadata.** Everything is treated as a resource with key-value labels (the `resource` table). Use this for filtering and arbitrary metadata storage.
7. **`data-model.sql` is the schema source of truth.** Any change to the database schema (adding tables, columns, constraints, triggers) **must** be reflected in `data-model.sql` first, then propagated to ORM models and migrations. The SQL file and the ORM models must always be in sync.

## Coding Standards & API Design

1. **Strict Dependency Injection (DI):** External clients (like MinIO, DB sessions, external APIs) must NEVER be initialized inside constructors or business logic functions. They must be injected from the outside (e.g. via FastAPI's `Depends` in the presentation layer, passing them to application services).
2. **Clean Code & Imports:** Standardize your code. Group imports properly (stdlib, third-party, local), sort them, and do NOT place imports inside functions. While you shouldn't get stuck in a formatter loop, always try to write clean, properly-styled code from the start.
3. **API Route Naming:** Follow this strict RESTful nested resource pattern with custom verbs when necessary:
   `/parent_resource/{parent_resource_id}/child_resource/{child_resource_id}:custom_verb`
   *(e.g., `/datasets/upload` should be `/datasets:upload` or `/models/{model_id}:upload`)*
4. **No Exposed Internal IDs:** Database primary keys and foreign keys are internal only. Public APIs must not expose UUID primary keys. User-facing routes and responses must use immutable, server-generated slugs plus business keys such as version numbers. Slugs should be derived from names, unique per user, and treated as stable API identifiers.

## Testing & Verification

### Requirements

After implementing any feature, modifying existing code, or fixing a bug, you **must** write and execute tests. Testing is not optional. **Every function must be thoroughly tested.** This includes normal happy-path cases, boundary/edge cases, and failure modes. Test undercoverage is unacceptable.

### Test Levels

- **Unit Tests:** Test individual functions, domain entities, business logic, and utility functions in isolation.
- **Integration Tests:** Test interactions between modules and external infrastructure (e.g., Control Plane ↔ PostgreSQL, MinIO webhooks, Grafana API provisioning).
- **End-to-End (E2E) Tests:** Validate full user journeys across services (e.g., SDK triggers deployment → Deployment Service provisions → Edge Gateway serves inference).

### Test Coverage Scope

- **Happy path:** Feature works as intended under normal conditions.
- **Error handling:** Invalid inputs, network failures, unauthenticated requests.
- **Platform edge cases:** Zombie runs (crash during training), OOM scenarios (large dataset uploads), concurrent deployments (task queue contention).

### Strict Documentation Alignment

All tests must follow the architectural patterns documented in `docs/`:
- Dataset upload tests must simulate the **pre-signed URL** workflow — the Control Plane never touches file bytes.
- Deployment tests must validate the **asynchronous, event-driven** nature — no synchronous blocking.
- Metric tests must validate that resources use the **key-value metadata** pattern correctly.

### Makefile Integration

All test commands must be registered in the root `Makefile`. The following targets must exist and pass:

```makefile
test-unit:           # Run unit tests for all Python services
test-integration:    # Run integration tests (requires running infrastructure)
test-e2e:            # Run end-to-end tests across the full stack
test:                # Run all tests (unit + integration + e2e)
```

Each Python service should also have its own local test targets:

```makefile
test-control-plane:  # Run all tests for the control plane
test-sdk:            # Run all tests for the SDK
test-deployment:     # Run all tests for the deployment service
```

### Self-Verification

You **must** execute the test suite yourself before concluding any task:

```bash
# Run from the repository root
make test
```

If any test fails, debug and fix the issue before reporting completion. Do not submit work with failing tests.

## Running the Platform Locally

```bash
# Start Minikube before running the platform.
minikube start
minikube tunnel

# Create local Kubernetes secrets. This file is ignored by git.
cp k8s/base/secret.example.env k8s/base/secret.env
# Edit k8s/base/secret.env before first deploy.

# Add these hosts to /etc/hosts, pointing at the Minikube tunnel IP:
# dashboard.mldlc.local api.mldlc.local gateway.mldlc.local minio.mldlc.local
# console.minio.mldlc.local gitea.mldlc.local grafana.mldlc.local

# Build local images and apply Kubernetes manifests.
make kube-up

# Check cluster state.
make kube-status
```

The dashboard is available at `http://dashboard.mldlc.local`. The API is available at `http://api.mldlc.local/api/v1`.
The model inference gateway is available at `http://gateway.mldlc.local`.
PostgreSQL is available through ingress TCP forwarding at `127.0.0.1:15432`.
