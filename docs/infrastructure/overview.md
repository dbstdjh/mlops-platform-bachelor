# Infrastructure Overview

The MLOps platform utilizes a distributed infrastructure stack designed to run locally on Kubernetes/Minikube while enforcing production-grade architectural patterns. The infrastructure prioritizes strict separation of concerns, asynchronous processing, and robust networking solutions to avoid common deployment pitfalls.

## Core Components

- **Control Plane API (FastAPI):** The central orchestrator. It manages metadata, provisions resources, and generates secure access tokens (e.g., pre-signed URLs), but deliberately avoids processing heavy payloads (like datasets or model weights) to prevent resource exhaustion.
- **PostgreSQL:** The universal state store. Beyond relational metadata, it also serves as a lightweight **message broker** for event-driven tasks.
- **MinIO:** The S3-compatible object storage layer. It hosts two buckets: `datasets` (with a webhook for event-driven status updates) and `models` (for model weights, confirmed synchronously). It also acts as the underlying storage backend for Gitea.
- **Gitea:** The artifact and source code registry. It manages user Git repositories and functions as the Docker container registry for deployed models.
- **Kubernetes (Minikube):** The execution environment where all user models and their inference containers are deployed and managed.
- **Deployment Service (Python):** An event-driven worker triggered via PostgreSQL `LISTEN/NOTIFY`. It claims deployment tasks, orchestrates container provisioning in Minikube, and polls the Kubernetes API for pod health.
- **Edge Gateway (Go):** The primary entry point for all model inference traffic.

## Architectural Workflows

### 1. The Edge Gateway Pattern
Deploying API Gateways as sidecars inside every Minikube pod introduces severe networking complexities, including Docker-to-Minikube routing loops and CORS challenges.

To solve this, the platform utilizes an **Edge Gateway Pattern**:
- A single Go-based API Gateway runs locally next to the Control Plane.
- All inference traffic from the web UI or SDK is routed to this Gateway (`localhost:8080`).
- The Gateway intercepts the request, validates the JWT, logs the payload to PostgreSQL (for observability and drift monitoring), and proxies the traffic directly to the internal Minikube IP of the target model container.

### 2. Large Data Handling & Storage
To protect the Control Plane from Out-Of-Memory (OOM) crashes when handling multi-gigabyte datasets, all heavy data transfers bypass the API.
- **Pre-signed URLs:** The SDK requests a temporary, secure URL from the Control Plane and streams data directly to MinIO.
- **Event-Driven Confirmation:** MinIO is configured to trigger webhooks back to the Control Plane once an upload completes, updating the dataset's status asynchronously.
- **Unified Backups:** Gitea routes all of its storage (LFS, Docker packages, etc.) directly into MinIO, ensuring that all platform state is consolidated between the PostgreSQL volume and the MinIO volume.

### 3. Asynchronous Model Deployments
Deployments are decoupled from the synchronous API to ensure resilience.
- When a deployment is requested, the Control Plane inserts a task row into the `deployment_task` table in PostgreSQL. A database trigger automatically fires a `pg_notify` signal on a dedicated channel.
- The **Deployment Service** is connected to PostgreSQL via `LISTEN` on that channel. Upon receiving the signal, it claims the task using `SELECT FOR UPDATE SKIP LOCKED`, pulls the required Docker image from Gitea or model file from MinIO, and interacts with the Kubernetes API to spin up the resources.
- After provisioning, the service polls the Kubernetes API for pod health, updating the deployment status once the endpoint is active and healthy.
