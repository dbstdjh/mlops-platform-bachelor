# Scikit-Learn Pickle Server

Global prebuilt inference image for `.pkl` and `.pickle` scikit-learn artifacts.

The container is intentionally platform-light: it does not authenticate requests, read deployment records, or talk to MinIO. The Deployment Service provides the model artifact on disk and sets `MODEL_PATH`; the Edge Gateway validates JWTs and request schemas before proxying traffic here.

## Runtime Contract

- `GET /health`: process liveness.
- `GET /ready`: model readiness. Returns `503` when the artifact failed to load.
- `POST /predict`: schema-flexible JSON inference endpoint.

## Environment

- `MODEL_PATH`: local model artifact path. Defaults to `/models/model.pkl`.
- `MLDLC_INPUT_KEY`: optional request field to extract before normalization.
- `MLDLC_INPUT_MODE`: `auto`, `raw`, `array`, or `dataframe`. Defaults to `auto`.
- `MLDLC_PREDICT_METHOD`: `predict`, `predict_proba`, `decision_function`, `transform`, or `call`. Defaults to `predict`.
- `MLDLC_RESPONSE_KEY`: response field name. Defaults to `predictions`.

## Global Registry Image

This is platform inventory, not a tenant-owned custom image. Publish it under the reserved global Gitea owner:

```bash
make publish-prebuilt-images
```

Expected tags:

```text
gitea.mldlc.local/mldlc/sklearn-pickle-server:0.1.0
gitea.mldlc.local/mldlc/sklearn-pickle-server:dev
```

Local Gitea is HTTP-only. Docker and Minikube must trust `gitea.mldlc.local` as an insecure local registry before push/pull will work.
