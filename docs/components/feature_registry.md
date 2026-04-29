# Feature Registry

The Feature Registry module operates as a primitive data repository centered around versioned "datasets". It supports importing Pandas DataFrames, Numpy arrays, CSV and Parquet files via the SDK. All raw data is stored in MinIO.

## Public Identity Model
Datasets must not expose internal database UUIDs through the public API.

- Every logical dataset receives an immutable, server-generated `slug`.
- The slug is derived from the submitted dataset name, made unique per user, and then reused for every future version of that dataset.
- The external dataset identity is therefore `(current_user, dataset_slug, version)`.
- Database primary keys remain internal implementation details used only for joins and foreign keys.

## The OOM (Out-Of-Memory) Bottleneck
A critical architectural decision was made to prevent the Control Plane API from directly handling dataset payloads.

**The Problem:** If the SDK sends a 2GB dataset to a FastAPI endpoint, the Python process must load the entire 2GB payload into RAM before forwarding it to MinIO. Multiple concurrent uploads would inevitably trigger an OOM-kill by Kubernetes.

**The Solution:** FastAPI **never** touches the actual file bytes. The system relies entirely on **Pre-signed URLs**.

## Workflows

### Push Workflow
1. **Initiation:** The user has a DataFrame in their local environment and runs `mlops.upload_dataset()`.
2. **Local Conversion:** The SDK silently converts the dataset to Parquet in-memory.
3. **URL Request:** The SDK requests a pre-signed upload URL from FastAPI.
4. **State Initialization:** FastAPI resolves or creates an immutable dataset slug, creates a `PENDING` dataset version in PostgreSQL, and returns the pre-signed URL.
5. **Direct Upload:** The SDK streams the file directly to MinIO, completely bypassing the Python backend.
6. **Webhook Confirmation:** MinIO fires a webhook to FastAPI confirming the upload, prompting FastAPI to update the dataset status to `READY`.

### Pull Workflow
1. **The Request:** The user runs `mlops.get_dataset("dataset_name")`. The SDK sends a request to FastAPI.
2. **The Resolution:** FastAPI queries PostgreSQL for the latest object path associated with that dataset where the status is `READY`.
3. **The Ticket Generation:** FastAPI utilizes internal credentials to generate a temporary, cryptographically signed `GET` URL for the specific object path in MinIO.
4. **The Handshake:** FastAPI returns only the URL to the SDK.
5. **The Direct Ingestion:** The SDK passes the URL directly into its data processing library (e.g., `pd.read_parquet()`), pulling the bytes straight from MinIO into local RAM, bypassing the API.

## API Shape
The API should use slug-based dataset identity rather than UUIDs.

- `POST /datasets:upload`
- `POST /datasets:confirm_upload`
- `GET /datasets`
- `GET /datasets/{dataset_slug}/versions/{version}`
- `GET /datasets/{dataset_slug}:download`
- `GET /datasets/{dataset_slug}/versions/{version}:download`

## MinIO Webhook Architecture
To achieve step 6 of the Push Workflow, MinIO is configured to trigger a webhook directly to the Control Plane API.

- **Definition:** MinIO defines the webhook destination declaratively via environment variables (e.g., `MINIO_NOTIFY_WEBHOOK_ENDPOINT_fastapi`).
- **Binding:** A startup script (`minio-init`) uses the MinIO Client (`mc`) to attach this webhook specifically to `put` events on the `datasets` bucket.
- **Payload:** MinIO sends a standard AWS S3 Event Notification JSON. FastAPI parses this JSON body to locate the uploaded file path (typically under `Records[0].s3.object.key`).
