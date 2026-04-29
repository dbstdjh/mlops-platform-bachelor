from __future__ import annotations

import asyncio
import pickle

import pandas as pd
import pandas.testing as pdt
import pytest


async def confirm_uploaded_dataset(control_plane_client, signed_url: str) -> None:
    object_key = signed_url.split("/datasets/", maxsplit=1)[1].split("?", maxsplit=1)[0]
    response = await control_plane_client.post(
        "/api/v1/datasets:confirm_upload",
        json={"Records": [{"s3": {"object": {"key": object_key}}}]},
    )
    assert response.status_code == 200


async def upload_ready_dataset(sdk_client, control_plane_client, name: str):
    captured = {}
    original_upload = sdk_client._upload_to_signed_url

    def wrapped(upload_url: str, payload: bytes) -> None:
        captured["url"] = upload_url
        original_upload(upload_url, payload)

    sdk_client._upload_to_signed_url = wrapped
    dataset = await asyncio.to_thread(
        sdk_client.upload_dataset,
        name,
        pd.DataFrame({"feature": [1, 2], "target": [0, 1]}),
        wait=False,
    )
    await confirm_uploaded_dataset(control_plane_client, captured["url"])
    return await asyncio.to_thread(sdk_client._wait_for_dataset_ready, dataset.slug, dataset.version, 5.0)


@pytest.mark.asyncio
async def test_sdk_exchanges_api_key_for_jwt_via_real_auth_flow(sdk_client):
    datasets = await asyncio.to_thread(sdk_client.list_datasets)

    assert datasets == []
    assert sdk_client._access_token is not None


@pytest.mark.asyncio
async def test_sdk_uploads_and_downloads_datasets_through_signed_urls(sdk_client, control_plane_client):
    source = pd.DataFrame({"feature": [1, 2, 3], "target": [0, 1, 0]})
    captured = {}
    original_upload = sdk_client._upload_to_signed_url

    def wrapped(upload_url: str, payload: bytes) -> None:
        captured["url"] = upload_url
        original_upload(upload_url, payload)

    sdk_client._upload_to_signed_url = wrapped
    dataset = await asyncio.to_thread(
        sdk_client.upload_dataset,
        "sdk-dataset",
        source,
        wait=False,
        labels={"suite": "integration"},
    )

    await confirm_uploaded_dataset(control_plane_client, captured["url"])
    ready_dataset = await asyncio.to_thread(sdk_client._wait_for_dataset_ready, dataset.slug, dataset.version, 5.0)
    downloaded = await asyncio.to_thread(sdk_client.download_dataset, ready_dataset.slug, ready_dataset.version)

    assert ready_dataset.status == "READY"
    pdt.assert_frame_equal(downloaded, source)


@pytest.mark.asyncio
async def test_sdk_logs_runs_and_models_against_real_control_plane(sdk_client, control_plane_client):
    dataset = await upload_ready_dataset(sdk_client, control_plane_client, "sdk-tracking-dataset")
    experiment = await asyncio.to_thread(sdk_client.create_experiment, "sdk-tracking", ["loss", "accuracy"])
    repository = await asyncio.to_thread(sdk_client.create_repository, "sdk-models")

    def run_workflow():
        with sdk_client.start_run(experiment.slug, dataset=dataset, labels={"stage": "train"}) as run:
            run.log_metric("loss", 1.0, step=0)
            run.log_metrics({"loss": 0.7, "accuracy": 0.9}, step=1)
            return run.log_model(repository.slug, "sdk-model", "1.0", {"weights": [1, 2, 3]})

    model = await asyncio.to_thread(run_workflow)
    run_info = await asyncio.to_thread(sdk_client.get_run, experiment.slug, 1)
    history = await asyncio.to_thread(sdk_client.get_run_metric_history, experiment.slug, 1, "loss")
    comparison = await asyncio.to_thread(sdk_client.get_experiment_metric_history, experiment.slug, "loss")
    restored_model = await asyncio.to_thread(
        sdk_client.download_model,
        repository.slug,
        "1.0",
        loader=lambda path: pickle.loads(path.read_bytes()),
    )

    assert model.status == "READY"
    assert model.file_type == "pickle"
    assert run_info.status == "COMPLETED"
    assert run_info.model.repository_slug == repository.slug
    assert list(history["step"]) == [0, 1]
    assert list(comparison["run_number"]) == [1, 1]
    assert restored_model == {"weights": [1, 2, 3]}


@pytest.mark.asyncio
async def test_sdk_preserves_uploaded_model_filename_for_path_artifacts(
    sdk_client,
    control_plane_client,
    tmp_path,
):
    repository = await asyncio.to_thread(sdk_client.create_repository, "sdk-file-models")
    artifact_path = tmp_path / "crappy-shit.pkl"
    payload = pickle.dumps({"model": "from-path"})
    artifact_path.write_bytes(payload)

    captured = {}
    original_upload = sdk_client._upload_to_signed_url

    def wrapped(upload_url: str, content: bytes) -> None:
        captured["url"] = upload_url
        original_upload(upload_url, content)

    sdk_client._upload_to_signed_url = wrapped
    model = await asyncio.to_thread(
        sdk_client.log_model,
        repository.slug,
        "sdk-file-model",
        "1.0",
        artifact_path,
    )

    object_key = captured["url"].split("/models/", maxsplit=1)[1].split("?", maxsplit=1)[0]
    response = await control_plane_client.post(
        "/api/v1/models:confirm_upload",
        json={"Records": [{"s3": {"object": {"key": object_key}}}]},
    )
    assert response.status_code == 200

    downloaded_path = await asyncio.to_thread(
        sdk_client.download_model,
        repository.slug,
        "1.0",
        destination=tmp_path / "downloaded.pkl",
    )

    assert model.status == "READY"
    assert model.file_type == "pickle"
    assert object_key.endswith("/crappy-shit.pkl")
    assert downloaded_path.read_bytes() == payload
