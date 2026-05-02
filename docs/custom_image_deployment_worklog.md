# Custom Image Deployment Worklog

Date: 2026-05-01

This document records the custom Docker image deployment work done during the long debugging session. It is intentionally practical and narrative: what was added, what broke, why it broke, and what the current working path is.

## Executive Summary

We added a new Artifact Registry / custom image deployment workflow backed by Gitea container packages.

Users can now:

- enable the `custom_deployments` feature for their own account,
- get a managed per-user Gitea identity,
- create persistent Docker registry tokens whose plaintext is shown once,
- push custom Docker images to Gitea,
- list those images through the Control Plane API,
- deploy an image tag through the existing async deployment pipeline.

The verified end-to-end path now works locally:

```bash
cd custom-image-demo
uv run python build_and_push.py
uv run python deploy_image.py
```

The final successful deployment reached `ACTIVE` and responded to `/predict`:

```json
{"model":"custom-image-demo","version":"1.0.0","predictions":["high","low"],"scores":[12.5,4.5]}
```

## Public API Added

Artifact Registry routes live under:

```text
/api/v1/artifact-registry
```

Endpoints:

```text
GET  /artifact-registry/status
POST /artifact-registry:enable
GET  /artifact-registry/tokens
POST /artifact-registry/tokens
POST /artifact-registry/tokens/{token_name}:revoke
GET  /artifact-registry/images
POST /artifact-registry/images/{image_name}/tags/{tag}/deployments
```

Important naming decision:

- We did not use `from_image` as a verb-style endpoint.
- Image deployments are nested under image/tag resources:

```text
POST /artifact-registry/images/{image_name}/tags/{tag}/deployments
```

## Core Product Semantics

Docker registry tokens are persistent until revoked.

The "one-time" part is only the plaintext display:

- token is created in Gitea,
- plaintext token is returned once by the API,
- platform does not store user-visible token plaintext,
- token can later be listed without plaintext,
- token can be revoked by name.

## Control Plane Changes

New module: Artifact Registry.

Major files added or changed:

```text
control-plane/src/core/entities/artifact_registry.py
control-plane/src/core/ports/artifact_registry.py
control-plane/src/application/artifact_registry_service.py
control-plane/src/infrastructure/artifact_registry/gitea.py
control-plane/src/presentation/api/v1/artifact_registry.py
control-plane/src/presentation/dependencies.py
control-plane/src/main.py
control-plane/src/config.py
data-model.sql
```

What changed:

- Added `custom_deployments` to the `feature` seed data.
- Reused `user_feature_config` for per-user enablement.
- Stored Gitea registry metadata in `user_feature_config.config_data`.
- Stored the backend proxy token encrypted with Fernet.
- Added `GITEA_PUBLIC_URL`, separate from internal `GITEA_URL`.
- Added Gitea HTTP adapter.
- Added image deployment creation path.
- Extended deployment responses with:
  - `source_type`
  - `image_ref`

Gitea adapter details:

- `GITEA_URL` is used internally by the Control Plane.
- `GITEA_PUBLIC_URL` is used to build user-facing Docker references.
- Local final public registry is:

```text
gitea.mldlc.local:80
```

Important compatibility fix:

Gitea 1.26 requires `source_id` and `login_name` when patching a user through:

```text
PATCH /api/v1/admin/users/{username}
```

The adapter now sends:

```json
{
  "source_id": 0,
  "login_name": "<username>",
  "password": "...",
  "must_change_password": false,
  "prohibit_login": false
}
```

Without this, token creation failed with:

```text
[LoginName]: Required
```

## Deployment Service Changes

Major files added or changed:

```text
deployment-service/src/deployment_service/db.py
deployment-service/src/deployment_service/kubernetes_resources.py
deployment-service/src/deployment_service/kubernetes_client.py
deployment-service/src/deployment_service/secrets.py
deployment-service/pyproject.toml
deployment-service/tests/unit/test_db.py
deployment-service/tests/unit/test_kubernetes_resources.py
deployment-service/tests/unit/test_kubernetes_client.py
```

What changed:

- Deployment specs now support two source types:
  - file-backed model deployments,
  - image-backed deployments.
- Image deployments skip the MinIO init container.
- Image deployments use the custom image directly as the serving container.
- Deployment Service generates an image pull secret for the deployment.
- Pull secret is based on the encrypted per-user Gitea proxy token from `user_feature_config`.
- Deployment Service deletes the image pull secret when deleting the deployment.
- Added Fernet decrypt support.
- Added `cryptography` dependency.

RBAC change:

Deployment Service now has permission to manage Kubernetes secrets:

```yaml
resources:
  - secrets
verbs:
  - get
  - create
  - patch
  - delete
```

Why it needs that:

- Kubernetes needs an `imagePullSecret` to pull private images from Gitea.
- The secret is per deployment / per image pull credential.
- It is cleaned up when the deployment is deleted.

Bug fixed during final deployment test:

`user_feature_config.config_data` came back from asyncpg as a JSON string in the Deployment Service, but code treated it as a dict.

Failure:

```text
AttributeError: 'str' object has no attribute 'get'
```

Fix:

```text
deployment-service/src/deployment_service/db.py
```

now defensively decodes config values:

- `None` -> `{}`
- `dict` -> unchanged
- JSON string -> `json.loads(...)`
- mapping-like fallback -> `dict(value)`

Added tests in:

```text
deployment-service/tests/unit/test_db.py
```

## SDK Changes

Major files changed:

```text
sdk/src/mldlc/client.py
sdk/src/mldlc/models.py
sdk/src/mldlc/__init__.py
sdk/tests/unit/test_client.py
```

Added SDK methods for:

- enabling custom deployments,
- reading artifact registry status,
- creating/listing/revoking registry tokens,
- listing pushed custom images,
- deploying an image tag.

The demo uses these SDK methods.

## Dashboard Changes

Dashboard Account page was extended with custom deployment / artifact registry controls.

It now supports:

- enabling custom deployments,
- viewing registry status,
- creating registry tokens,
- showing token plaintext once,
- revoking tokens,
- listing custom images/tags.

Relevant areas:

```text
dashboard/src
dashboard tests
```

## Kubernetes Changes

Major files added or changed:

```text
k8s/base/configmap.yaml
k8s/base/gitea.yaml
k8s/base/gitea-db-init-job.yaml
k8s/base/ingress.yaml
k8s/base/kustomization.yaml
k8s/base/deployment-service.yaml
Makefile
scripts/bootstrap-gitea.sh
```

### Gitea Public URL

Local registry public URL is now:

```text
http://gitea.mldlc.local:80
```

This matters because Docker behaved more predictably when the registry ref was explicit:

```text
gitea.mldlc.local:80/<managed-user>/<image>:<tag>
```

The config is:

```yaml
GITEA_PUBLIC_URL: http://gitea.mldlc.local:80
```

and Gitea gets:

```yaml
GITEA__server__ROOT_URL: http://gitea.mldlc.local:80
```

### Gitea Install Lock

Gitea initially served the first-run install page.

We added:

```yaml
GITEA__security__INSTALL_LOCK: "true"
```

This lets Gitea start as an installed instance from env config instead of waiting for browser setup.

### Gitea Separate Database

Initial mistake:

Gitea was pointed at the same Postgres database as the platform Control Plane.

Failure:

```text
Table user column id db type is UUID, struct type is BIGSERIAL
sync database struct error: pq: column "lower_name" of relation "user" contains null values
```

Cause:

- Control Plane has its own `"user"` table.
- Gitea also has a `"user"` table.
- They cannot share one database/schema.

Fix:

Added:

```text
k8s/base/gitea-db-init-job.yaml
```

It creates a separate `gitea` database:

```sql
CREATE DATABASE gitea OWNER mldlc
```

and Gitea now uses:

```yaml
GITEA__database__NAME: gitea
```

### Gitea Deployment Strategy

Gitea uses a PVC at `/data`.

Rolling updates caused the old and new pod to overlap and fight over Gitea queue DB files:

```text
unable to lock level db at /data/gitea/queues/common: resource temporarily unavailable
Unable to create notification-service queue
```

Fix:

```yaml
strategy:
  type: Recreate
```

in:

```text
k8s/base/gitea.yaml
```

### Ingress Upload Size

Docker image push initially failed with:

```text
413 Request Entity Too Large
```

Cause:

- NGINX ingress default request body size was too low for Docker layer uploads.

Fix:

```yaml
nginx.ingress.kubernetes.io/proxy-body-size: "0"
nginx.ingress.kubernetes.io/proxy-request-buffering: "off"
```

in:

```text
k8s/base/ingress.yaml
```

### Gitea Bootstrap Script

Added:

```text
scripts/bootstrap-gitea.sh
```

It:

- waits for Gitea rollout,
- runs `gitea migrate`,
- creates an admin user if needed,
- generates a fresh admin token,
- patches `platform-secret` with `GITEA_ADMIN_TOKEN`,
- restarts the Control Plane API,
- waits for API rollout.

This is needed because `kube-reset` happens often and Gitea must become usable without manual browser setup.

Make target:

```make
kube-bootstrap-gitea
```

Called during:

```make
kube-up
```

### Kube Reset

`make kube-reset` originally deleted the namespace but left old PVs behind.

That caused a fresh namespace to sometimes bind to stale data, then `db-init` failed:

```text
psql:/schema/data-model.sql:13: ERROR: relation "run_status" already exists
```

We decided not to make `data-model.sql` idempotent.

Instead, `kube-reset` now actually nukes leftover storage:

```make
kube-reset:
	$(KUBECTL) delete namespace $(NAMESPACE) --ignore-not-found=true
	$(KUBECTL) wait --for=delete namespace/$(NAMESPACE) --timeout=180s || true
	$(MAKE) kube-reset-storage
	$(MAKE) kube-up
```

New target:

```make
kube-reset-storage
```

It deletes PVs whose claim belonged to the namespace.

This was verified:

```text
Deleting persistent volumes from namespace mldlc: ...
job.batch/db-init condition met
job.batch/gitea-db-init condition met
job.batch/minio-init condition met
Gitea bootstrap complete
deployment "dashboard" successfully rolled out
```

## Docker Desktop Local Configuration

Outside the repo, Docker Desktop daemon config was updated:

```text
/home/stas/.docker/daemon.json
```

It now contains:

```json
{
  "insecure-registries": [
    "gitea.mldlc.local",
    "gitea.mldlc.local:80"
  ]
}
```

Why:

- Local Gitea is served over plain HTTP through Minikube ingress.
- Docker must treat the registry as insecure.

Docker Desktop must be restarted after editing this file.

Important side effect:

- Restarting Docker Desktop stops Minikube.
- After Docker Desktop restart, run:

```bash
minikube start
minikube kubectl -- -n ingress-nginx patch svc ingress-nginx-controller -p '{"spec":{"type":"LoadBalancer"}}'
minikube tunnel --bind-address=127.0.0.1
```

The tunnel may require sudo because it binds ports 80/443.

## Custom Image Demo

New top-level folder:

```text
custom-image-demo/
```

Important files:

```text
custom-image-demo/app.py
custom-image-demo/Dockerfile
custom-image-demo/build_and_push.py
custom-image-demo/deploy_image.py
custom-image-demo/pyproject.toml
custom-image-demo/uv.lock
custom-image-demo/.env
custom-image-demo/.env.example
custom-image-demo/README.md
```

The demo is a simple Python HTTP server using only the standard library for runtime.

It implements the required custom image contract:

```text
GET  /health
GET  /ready
POST /predict
```

Example response:

```json
{
  "model": "custom-image-demo",
  "version": "1.0.0",
  "predictions": ["high", "low"],
  "scores": [12.5, 4.5]
}
```

### Demo Env Loading

Initially the demo silently loaded:

```text
sdk/.env
```

That caused stale API key failures:

```text
mldlc.errors.AuthenticationError: Invalid API key credentials
```

Fix:

- `custom-image-demo/.env` now wins.
- `sdk/.env` is only a fallback if local `.env` is missing.
- `custom-image-demo/.env` exists as the paste target for fresh credentials.

Required:

```dotenv
MLDLC_BASE_URL=http://api.mldlc.local
MLDLC_USERNAME=your@email
MLDLC_API_KEY=mlp_...
```

Optional:

```dotenv
MLDLC_CUSTOM_IMAGE_NAME=custom-image-demo
MLDLC_CUSTOM_IMAGE_TAG=latest
MLDLC_CUSTOM_IMAGE_PLATFORM=linux/amd64
MLDLC_REGISTRY_TOKEN=
MLDLC_REGISTRY_TOKEN_NAME=
MLDLC_CUSTOM_DEPLOYMENT_NAME=
MLDLC_DEPLOY_TIMEOUT_SECONDS=300
MLDLC_DEPLOY_POLL_INTERVAL_SECONDS=5
MLDLC_READY_TIMEOUT_SECONDS=120
MLDLC_POLL_INTERVAL_SECONDS=2
```

### Demo Build/Push

Initial push problems:

1. stale SDK API key,
2. Gitea not installed / no admin token,
3. Gitea admin user patch required `login_name`,
4. Docker credential helper/GPG issue,
5. Docker trying HTTPS against local ingress cert,
6. NGINX ingress 413 upload limit,
7. Docker Desktop pushed an OCI image index/provenance shape that Gitea rejected.

Final build/push strategy:

```bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  --push \
  -t gitea.mldlc.local:80/<managed-user>/custom-image-demo:latest \
  custom-image-demo
```

This is now implemented in:

```text
custom-image-demo/build_and_push.py
```

Why provenance/SBOM are disabled:

Gitea accepted the normal image manifest, then Docker tried to commit an extra top-level index manifest and Gitea returned:

```text
404 Not Found
```

The log showed:

```text
PUT /v2/.../manifests/latest 201 Created
PUT /v2/.../manifests/latest 404 Not Found
```

Disabling attestations and forcing one platform produced a plain manifest that Gitea accepted.

Verified pushed image:

```text
gitea.mldlc.local:80/mldlc-bdcb2e62b824/custom-image-demo:latest
```

### Demo Deploy

Command:

```bash
cd custom-image-demo
uv run python deploy_image.py
```

The first attempt failed because Deployment Service crashed on JSON config decoding.

After fixing and restarting Deployment Service, the deployment succeeded:

```text
Deployment custom-image-demo-latest-20260430205914-3c0bd700: PENDING
Deployment custom-image-demo-latest-20260430205914-3c0bd700: DEPLOYING
Deployment custom-image-demo-latest-20260430205914-3c0bd700: ACTIVE
```

Endpoint:

```text
http://127.0.0.1:23002/predict
```

Smoke request:

```bash
curl -X POST 'http://127.0.0.1:23002/predict' \
  -H 'Content-Type: application/json' \
  --data '{"instances":[[2.5,4.0,6.0],[1.0,1.5,2.0]]}'
```

Response:

```json
{"model":"custom-image-demo","version":"1.0.0","predictions":["high","low"],"scores":[12.5,4.5]}
```

## Important Failure Timeline

### 1. API key was stale

Error:

```text
AuthenticationError: Invalid API key credentials
```

Cause:

- demo loaded `sdk/.env`,
- API key there no longer existed in the reset database.

Fix:

- demo local `.env`,
- local `.env` wins over `sdk/.env`.

### 2. Gitea admin token missing

Error:

```text
Gitea admin token is not configured
```

Cause:

- `GITEA_ADMIN_TOKEN=` was empty,
- Gitea itself was still in first-run setup mode.

Fix:

- Gitea bootstrap script,
- Makefile target,
- admin token generated and patched into Kubernetes secret.

### 3. Gitea shared the Control Plane database

Error:

```text
sync database struct error
Table user column id db type is UUID, struct type is BIGSERIAL
```

Cause:

- Gitea and Control Plane both used the `mldlc` database.

Fix:

- separate `gitea` database,
- `gitea-db-init` job.

### 4. Gitea user patch needed required fields

Error:

```text
[LoginName]: Required
```

Cause:

- Gitea 1.26 requires `source_id` and `login_name` for edit-user payload.

Fix:

- adapter sends both.

### 5. Docker/GPG credential helper issue

Error:

```text
gpg: public key decryption failed: Operation cancelled
```

Cause:

- Docker credential helper tried to unlock local credentials.

Resolution:

- user looked up/unlocked credentials,
- normal Docker config became usable.

### 6. Docker tried HTTPS

Error:

```text
tls: failed to verify certificate: x509: certificate is valid for ingress.local, not gitea.mldlc.local
```

Cause:

- local registry is HTTP,
- Docker did not fully treat the registry as insecure,
- registry URL lacked explicit `:80`.

Fix:

- Docker insecure registries:
  - `gitea.mldlc.local`
  - `gitea.mldlc.local:80`
- `GITEA_PUBLIC_URL=http://gitea.mldlc.local:80`
- Gitea root URL set to same.

### 7. Ingress upload too small

Error:

```text
413 Request Entity Too Large
```

Cause:

- NGINX ingress body-size limit.

Fix:

- `proxy-body-size: "0"`
- `proxy-request-buffering: "off"`

### 8. Gitea rejected Docker image index

Error:

```text
failed commit on ref "index-sha256:..."
PUT ... /manifests/latest: 404 Not Found
```

Cause:

- Docker Desktop/buildx pushed OCI index/provenance/SBOM style output.
- Gitea accepted the image manifest but rejected the extra top-level index commit.

Fix:

- `docker buildx build --platform linux/amd64 --provenance=false --sbom=false --push`

### 9. Deployment Service JSON decode crash

Error:

```text
AttributeError: 'str' object has no attribute 'get'
```

Cause:

- asyncpg returned JSON config as string.

Fix:

- decode config defensively in Deployment Service.

## Verification Performed

Control Plane / SDK / Deployment / Dashboard tests were run during implementation, including:

```text
control-plane unit tests
sdk unit tests
deployment-service unit tests
dashboard integration tests
dashboard build
model image tests
```

Focused final verification:

```bash
cd deployment-service && uv run pytest tests/unit -v
```

Result:

```text
16 passed
```

Demo script syntax check:

```bash
cd custom-image-demo
uv run python -m py_compile app.py build_and_push.py deploy_image.py
```

Result:

```text
passed
```

End-to-end custom image push:

```text
Pushed custom image:
gitea.mldlc.local:80/mldlc-bdcb2e62b824/custom-image-demo:latest
```

End-to-end custom image deployment:

```text
status=ACTIVE
```

Prediction endpoint smoke test:

```text
HTTP/1.0 200 OK
```

## Current Working Local Procedure

Start/reset cluster:

```bash
make kube-reset
```

Start tunnel in a separate terminal:

```bash
minikube tunnel --bind-address=127.0.0.1
```

Paste fresh SDK credentials into:

```text
custom-image-demo/.env
```

Push custom image:

```bash
cd custom-image-demo
uv run python build_and_push.py
```

Deploy custom image:

```bash
uv run python deploy_image.py
```

Smoke test endpoint printed by deploy script:

```bash
curl -X POST '<DEPLOYMENT_URL>' \
  -H 'Content-Type: application/json' \
  --data '{"instances":[[2.5,4.0,6.0],[1.0,1.5,2.0]]}'
```

## Current Gotchas

### `minikube tunnel`

This must be running for local hostnames:

```text
api.mldlc.local
gitea.mldlc.local
dashboard.mldlc.local
```

It may require sudo to bind port 80.

If Docker Desktop restarts, Minikube usually stops. Run:

```bash
minikube start
minikube kubectl -- -n ingress-nginx patch svc ingress-nginx-controller -p '{"spec":{"type":"LoadBalancer"}}'
minikube tunnel --bind-address=127.0.0.1
```

### API keys after reset

`make kube-reset` nukes the database and storage.

Any existing API key becomes invalid.

Create/paste a fresh API key into:

```text
custom-image-demo/.env
```

### Docker insecure registry config

Docker Desktop must have:

```json
"insecure-registries": [
  "gitea.mldlc.local",
  "gitea.mldlc.local:80"
]
```

If changed, restart Docker Desktop.

### Gitea bootstrap token

Do not manually store a Gitea password for users.

The platform uses:

- global admin token only for provisioning,
- encrypted per-user proxy token for backend operations,
- user-created Docker registry tokens for local push.

### Custom images contract

Custom images must provide:

```text
GET /health
GET /ready
POST /predict
```

The Deployment Service and Edge Gateway expect this contract.

## Most Important Files Changed

Control Plane:

```text
control-plane/src/application/artifact_registry_service.py
control-plane/src/infrastructure/artifact_registry/gitea.py
control-plane/src/presentation/api/v1/artifact_registry.py
control-plane/src/presentation/dependencies.py
control-plane/src/config.py
data-model.sql
```

Deployment Service:

```text
deployment-service/src/deployment_service/db.py
deployment-service/src/deployment_service/kubernetes_client.py
deployment-service/src/deployment_service/kubernetes_resources.py
deployment-service/src/deployment_service/secrets.py
deployment-service/tests/unit/test_db.py
```

Kubernetes:

```text
k8s/base/configmap.yaml
k8s/base/deployment-service.yaml
k8s/base/gitea.yaml
k8s/base/gitea-db-init-job.yaml
k8s/base/ingress.yaml
k8s/base/kustomization.yaml
```

Automation:

```text
Makefile
scripts/bootstrap-gitea.sh
```

SDK:

```text
sdk/src/mldlc/client.py
sdk/src/mldlc/models.py
sdk/src/mldlc/__init__.py
```

Demo:

```text
custom-image-demo/
```

External local machine config:

```text
/home/stas/.docker/daemon.json
```

## Final Known Good State

At the end of the debugging session:

- `make kube-reset` completed successfully.
- Gitea bootstrapped automatically.
- Docker push to Gitea succeeded.
- `deploy_image.py` created an image-backed deployment.
- Deployment reached `ACTIVE`.
- `/predict` returned `200 OK`.

The custom image deployment workflow is now functionally verified locally.
