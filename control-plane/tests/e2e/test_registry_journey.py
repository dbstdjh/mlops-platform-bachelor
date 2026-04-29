import pickle

import httpx
import pytest


async def upload_bytes(url: str, payload: bytes) -> None:
    async with httpx.AsyncClient(trust_env=False) as storage_client:
        response = await storage_client.put(url, content=payload, headers={"content-type": "application/octet-stream"})
    assert response.status_code in {200, 201, 204}


async def download_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(trust_env=False) as storage_client:
        response = await storage_client.get(url)
    response.raise_for_status()
    return response.content


@pytest.mark.asyncio
async def test_phase_one_registry_journey(client):
    parquet_bytes = b"PAR1e2e-datasetPAR1"
    pickle_bytes = pickle.dumps({"model": "e2e", "framework": "pytest"})

    repository_response = await client.post(
        "/api/v1/repositories",
        json={"name": "e2e-repository", "labels": {"suite": "e2e"}},
    )
    assert repository_response.status_code == 201
    repository_slug = repository_response.json()["slug"]

    model_response = await client.post(
        f"/api/v1/repositories/{repository_slug}/models",
        json={
            "name": "e2e-model",
            "version": "1.0",
            "labels": {"framework": "pytest"},
        },
    )
    assert model_response.status_code == 201

    model_upload_response = await client.post(f"/api/v1/repositories/{repository_slug}/models/1.0:upload")
    assert model_upload_response.status_code == 200
    model_upload_url = model_upload_response.json()["upload_url"]
    model_object_key = model_upload_url.split("/models/", maxsplit=1)[1].split("?", maxsplit=1)[0]

    await upload_bytes(model_upload_url, pickle_bytes)

    model_confirm_response = await client.post(
        "/api/v1/models:confirm_upload",
        json={"Records": [{"s3": {"object": {"key": model_object_key}}}]},
    )
    assert model_confirm_response.status_code == 200
    assert model_confirm_response.json() == {"status": "ok"}

    model_download_response = await client.get(f"/api/v1/repositories/{repository_slug}/models/1.0:download")
    assert model_download_response.status_code == 200
    assert await download_bytes(model_download_response.json()["download_url"]) == pickle_bytes

    model_response = await client.get(f"/api/v1/repositories/{repository_slug}/models/1.0")
    assert model_response.status_code == 200
    assert model_response.json()["status"] == "READY"

    dataset_response = await client.post(
        "/api/v1/datasets:upload",
        json={"name": "e2e-dataset", "file_type": "parquet", "labels": {"suite": "e2e"}},
    )
    assert dataset_response.status_code == 201
    dataset_slug = dataset_response.json()["dataset_slug"]
    dataset_version = dataset_response.json()["version"]
    upload_url = dataset_response.json()["upload_url"]
    object_key = upload_url.split("/datasets/", maxsplit=1)[1].split("?", maxsplit=1)[0]

    await upload_bytes(upload_url, parquet_bytes)

    confirm_response = await client.post(
        "/api/v1/datasets:confirm_upload",
        json={"Records": [{"s3": {"object": {"key": object_key}}}]},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json() == {"status": "ok"}

    download_response = await client.get("/api/v1/datasets/e2e-dataset:download")
    assert download_response.status_code == 200
    assert await download_bytes(download_response.json()["download_url"]) == parquet_bytes

    dataset_version_response = await client.get(f"/api/v1/datasets/{dataset_slug}/versions/{dataset_version}")
    assert dataset_version_response.status_code == 200
    assert dataset_version_response.json()["status"] == "READY"


@pytest.mark.asyncio
async def test_phase_one_experiment_tracking_journey(client):
    dataset_response = await client.post(
        "/api/v1/datasets:upload",
        json={"name": "e2e-tracking-dataset", "file_type": "parquet", "labels": {"suite": "e2e"}},
    )
    assert dataset_response.status_code == 201
    dataset_slug = dataset_response.json()["dataset_slug"]
    dataset_version = dataset_response.json()["version"]
    dataset_upload_url = dataset_response.json()["upload_url"]
    dataset_object_key = dataset_upload_url.split("/datasets/", maxsplit=1)[1].split("?", maxsplit=1)[0]

    await upload_bytes(dataset_upload_url, b"PAR1tracking-datasetPAR1")
    dataset_confirm_response = await client.post(
        "/api/v1/datasets:confirm_upload",
        json={"Records": [{"s3": {"object": {"key": dataset_object_key}}}]},
    )
    assert dataset_confirm_response.status_code == 200

    experiment_response = await client.post(
        "/api/v1/experiments",
        json={
            "name": "e2e-experiment",
            "logged_data_template": ["loss", "accuracy"],
            "labels": {"suite": "e2e"},
        },
    )
    assert experiment_response.status_code == 201
    experiment_slug = experiment_response.json()["slug"]

    run_response = await client.post(
        f"/api/v1/experiments/{experiment_slug}/runs",
        json={"dataset_slug": dataset_slug, "dataset_version": dataset_version, "labels": {"stage": "train"}},
    )
    assert run_response.status_code == 201
    assert run_response.json()["dataset"] == {"dataset_slug": dataset_slug, "version": dataset_version}

    log_response = await client.post(
        f"/api/v1/experiments/{experiment_slug}/runs/1/steps",
        json={
            "items": [
                {"step": 0, "logged_data": {"loss": 1.0}},
                {"step": 1, "logged_data": {"loss": 0.8, "accuracy": 0.9}},
            ]
        },
    )
    assert log_response.status_code == 200

    repository_response = await client.post(
        "/api/v1/repositories",
        json={"name": "e2e-experiment-repository", "labels": {"suite": "e2e"}},
    )
    assert repository_response.status_code == 201
    repository_slug = repository_response.json()["slug"]

    model_response = await client.post(
        f"/api/v1/repositories/{repository_slug}/models",
        json={
            "name": "e2e-linked-model",
            "version": "1.0",
            "run": {"experiment_slug": experiment_slug, "run_number": 1},
        },
    )
    assert model_response.status_code == 201
    assert model_response.json()["run"] == {"experiment_slug": experiment_slug, "run_number": 1}

    complete_response = await client.post(f"/api/v1/experiments/{experiment_slug}/runs/1:complete")
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "COMPLETED"

    run_plot_response = await client.get(f"/api/v1/experiments/{experiment_slug}/runs/1/plots/loss")
    assert run_plot_response.status_code == 200
    assert [point["step"] for point in run_plot_response.json()["points"]] == [0, 1]

    experiment_plot_response = await client.get(f"/api/v1/experiments/{experiment_slug}/plots/loss")
    assert experiment_plot_response.status_code == 200
    assert experiment_plot_response.json()["series"][0]["run"] == {
        "experiment_slug": experiment_slug,
        "run_number": 1,
    }


@pytest.mark.asyncio
async def test_phase_one_failed_run_prevents_zombie_logging(client):
    experiment_response = await client.post(
        "/api/v1/experiments",
        json={"name": "e2e-failed-experiment", "logged_data_template": ["loss"]},
    )
    assert experiment_response.status_code == 201
    experiment_slug = experiment_response.json()["slug"]

    run_response = await client.post(f"/api/v1/experiments/{experiment_slug}/runs", json={})
    assert run_response.status_code == 201

    fail_response = await client.post(f"/api/v1/experiments/{experiment_slug}/runs/1:fail")
    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "FAILED"

    log_response = await client.post(
        f"/api/v1/experiments/{experiment_slug}/runs/1/steps",
        json={"items": [{"step": 2, "logged_data": {"loss": 0.4}}]},
    )
    assert log_response.status_code == 409
