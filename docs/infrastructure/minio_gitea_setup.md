# Storage and Registry Infrastructure (MinIO & Gitea)

The platform relies on Kubernetes/Minikube to orchestrate local instances of MinIO and Gitea. Together with PostgreSQL, these services form the foundational storage and artifact registry layer.

Rather than just standing up isolated services, MinIO and Gitea are deeply integrated to support specific MLOps workflows, such as event-driven dataset ingestion and unified storage management.

## 1. MinIO: Event-Driven Feature Registry Backend

MinIO acts as the S3-compatible object storage for the platform. It hosts two primary buckets:
- **`datasets`:** The destination for datasets uploaded via the Feature Registry. Configured with a webhook to notify the Control Plane on upload completion.
- **`models`:** The destination for model weights (`.pkl`, `.keras` files) uploaded during experiment tracking. Configured with its own webhook to notify the Control Plane on upload completion.

### The Upload Workflow
To prevent the FastAPI Control Plane from crashing due to Out-Of-Memory (OOM) errors when users upload large files (e.g., a 2GB Parquet file), the infrastructure uses a direct-to-storage flow:

1. **Ticket Generation:** The SDK asks the Control Plane for permission to upload. The Control Plane creates a `PENDING` record in PostgreSQL and returns a Pre-signed URL.
2. **Direct Streaming:** The SDK uses the Pre-signed URL to upload the file directly to MinIO, completely bypassing the Python backend.
3. **Webhook Notification:** MinIO is configured with a webhook targeting the Control Plane. The moment the upload finishes, MinIO sends a standard S3 Event Notification to the FastAPI webhook endpoint.
4. **State Resolution:** The Control Plane receives the webhook and marks the dataset as `READY` in PostgreSQL.

For model artifacts, the flow is also event-driven:

1. The SDK requests a pre-signed upload URL for a model version.
2. The SDK uploads the model bytes directly to the `models` bucket.
3. MinIO emits a webhook event to the Control Plane for the uploaded object.
4. The Control Plane resolves the `(user, repository_slug, version)` from the object key and marks the model as `READY`.

### Webhook Configuration
This event-driven flow is configured entirely via environment variables and an initialization container (`minio-init`), requiring no manual setup.

Inside the `minio` service, the webhook target is defined:
```yaml
environment:
  - MINIO_NOTIFY_WEBHOOK_ENABLE_fastapi=on
  - MINIO_NOTIFY_WEBHOOK_ENDPOINT_fastapi=http://api:8000/api/v1/datasets:confirm_upload
  - MINIO_NOTIFY_WEBHOOK_ENABLE_fastapi_models=on
  - MINIO_NOTIFY_WEBHOOK_ENDPOINT_fastapi_models=http://api:8000/api/v1/models:confirm_upload
```

The `minio-init` container then creates the bucket and binds the `put` (upload) event to the webhook:
```bash
# Setup Alias
/usr/bin/mc alias set myminio http://minio:9000 minioadmin minioadmin;

# Create the Buckets
/usr/bin/mc mb myminio/datasets --ignore-existing;
/usr/bin/mc mb myminio/models --ignore-existing;

# Attach the Webhook Event to 'put' (uploads) on the datasets bucket
/usr/bin/mc event add myminio/datasets arn:minio:sqs::fastapi:webhook --event put;

# Attach the Webhook Event to 'put' (uploads) on the models bucket
/usr/bin/mc event add myminio/models arn:minio:sqs::fastapi_models:webhook --event put;
```

## 2. Gitea: Artifact Registry and Unified Storage

Gitea serves as the platform's Artifact Registry. When users deploy custom models, Gitea acts as the Docker container registry that the Deployment Service pulls from.

### The Unified Storage Workflow
By default, Gitea stores its data (LFS files, avatars, attachments, and Docker packages) on the local filesystem. To simplify infrastructure management and disaster recovery, Gitea is configured to route **all** of its storage directly into MinIO.

This means the entire state of the platform (excluding the PostgreSQL database) lives in a single MinIO volume.

### Gitea MinIO Configuration
Gitea is configured via environment variables to utilize the internal MinIO network endpoint:

```yaml
environment:
  # Unified Storage Configuration (Routes EVERYTHING to MinIO)
  - GITEA__storage__STORAGE_TYPE=minio
  - GITEA__storage__MINIO_ENDPOINT=minio:9000
  - GITEA__storage__MINIO_ACCESS_KEY_ID=minioadmin
  - GITEA__storage__MINIO_SECRET_ACCESS_KEY=minioadmin
  - GITEA__storage__MINIO_BUCKET=gitea-bucket
  - GITEA__storage__MINIO_LOCATION=us-east-1
  - GITEA__storage__MINIO_USE_SSL=false
```
