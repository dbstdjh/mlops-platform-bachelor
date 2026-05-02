# Custom Image Demo

This folder contains a small custom model server that matches the platform's deployment contract:

- `GET /health`
- `GET /ready`
- `POST /predict`

The image has no Python package dependencies; it uses the standard library HTTP server.

## Prerequisites

From this folder, paste fresh SDK credentials into `.env`:

```dotenv
MLDLC_BASE_URL=http://api.mldlc.local
MLDLC_USERNAME=user@example.com
MLDLC_API_KEY=mlp_...
```

If `.env` does not exist, the scripts fall back to `../sdk/.env`.

Docker must be able to reach `gitea.mldlc.local`. If Gitea uses plain HTTP locally, Docker may need this registry marked as insecure in your Docker daemon config.

## Build And Push

```bash
uv run python build_and_push.py
```

Defaults:

- image name: `custom-image-demo`
- tag: `latest`
- platform: `linux/amd64`

Override them with:

```bash
MLDLC_CUSTOM_IMAGE_NAME=my-demo MLDLC_CUSTOM_IMAGE_TAG=v1 \
  uv run python build_and_push.py
```

The script:

1. Enables the Artifact Registry feature for your account.
2. Creates a Docker registry token unless `MLDLC_REGISTRY_TOKEN` is already set.
3. Logs Docker into your managed Gitea registry namespace.
4. Builds and pushes a single-platform image without provenance/SBOM attestations.
5. Pushes `gitea.mldlc.local:80/<managed-user>/<image>:<tag>`.

## Deploy

```bash
uv run python deploy_image.py
```

If you pushed a non-default name or tag:

```bash
MLDLC_CUSTOM_IMAGE_NAME=my-demo MLDLC_CUSTOM_IMAGE_TAG=v1 \
  uv run python deploy_image.py
```

The deployment script checks that the pushed tag is visible through the Artifact Registry API, creates an image-backed deployment, waits for it to become `ACTIVE`, and prints a test `curl`.

## Local Smoke Test

```bash
docker build -t custom-image-demo:local custom-image-demo
docker run --rm -p 8000:8000 custom-image-demo:local
curl http://127.0.0.1:8000/ready
curl -X POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  --data '{"instances":[[2.5,4.0,6.0],[1.0,1.5,2.0]]}'
```
