# MinIO and Gitea Infrastructure

The system relies on Docker Compose to orchestrate local instances of PostgreSQL, MinIO, and Gitea. Gitea is configured to use MinIO as its unified storage backend.

## Architecture
- **PostgreSQL:** Backs both the Control Plane and Gitea.
- **MinIO:** Handles direct S3 storage for datasets and acts as the backend for Gitea's artifacts.
- **Gitea:** Manages git repositories and Docker container registries.

## MinIO Webhook Configuration
To support the Feature Registry's event-driven dataset upload flow, MinIO is configured to trigger webhooks. This is done purely via environment variables and an initialization container.

### 1. Defining the Webhook (Control Plane Target)
Inside the `minio` service environment variables, a target named `fastapi` is defined:
```yaml
environment:
  - MINIO_NOTIFY_WEBHOOK_ENABLE_fastapi=on
  - MINIO_NOTIFY_WEBHOOK_ENDPOINT_fastapi=http://api:8000/api/v1/datasets/webhook
```

### 2. Binding the Event (`minio-init`)
An initialization container (`minio/mc`) runs a startup script to create buckets and attach the webhook:
```bash
# Setup Alias
/usr/bin/mc alias set myminio http://minio:9000 minioadmin minioadmin;

# Create the Bucket
/usr/bin/mc mb myminio/datasets --ignore-existing;

# Attach the Webhook Event to 'put' (uploads)
/usr/bin/mc event add myminio/datasets arn:minio:sqs::fastapi:webhook --event put;
```

## Gitea Unified Storage
Gitea is configured via environment variables to route all of its storage (LFS, avatars, attachments, packages) directly into MinIO.

```yaml
environment:
  - GITEA__storage__STORAGE_TYPE=minio
  - GITEA__storage__MINIO_ENDPOINT=minio:9000
  - GITEA__storage__MINIO_ACCESS_KEY_ID=minioadmin
  - GITEA__storage__MINIO_SECRET_ACCESS_KEY=minioadmin
  - GITEA__storage__MINIO_BUCKET=gitea-bucket
```
