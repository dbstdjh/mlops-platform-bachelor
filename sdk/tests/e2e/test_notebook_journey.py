from __future__ import annotations

import asyncio
import pickle

import pandas as pd
import pandas.testing as pdt
import pytest


@pytest.mark.asyncio
async def test_notebook_style_sdk_journey(sdk_client, control_plane_client):
    frame = pd.DataFrame({"feature": [10, 20], "target": [1, 0]})
    captured = {}
    original_upload = sdk_client._upload_to_signed_url

    def wrapped(upload_url: str, payload: bytes) -> None:
        captured["url"] = upload_url
        original_upload(upload_url, payload)

    sdk_client._upload_to_signed_url = wrapped
    uploaded_dataset = await asyncio.to_thread(
        sdk_client.upload_dataset,
        "e2e-notebook-dataset",
        frame,
        wait=False,
        labels={"suite": "e2e"},
    )

    object_key = captured["url"].split("/datasets/", maxsplit=1)[1].split("?", maxsplit=1)[0]
    confirm_response = await control_plane_client.post(
        "/api/v1/datasets:confirm_upload",
        json={"Records": [{"s3": {"object": {"key": object_key}}}]},
    )
    assert confirm_response.status_code == 200

    ready_dataset = await asyncio.to_thread(
        sdk_client._wait_for_dataset_ready,
        uploaded_dataset.slug,
        uploaded_dataset.version,
        5.0,
    )
    experiment = await asyncio.to_thread(
        sdk_client.create_experiment,
        "e2e-sdk-experiment",
        ["loss", "accuracy"],
        {"suite": "e2e"},
    )
    repository = await asyncio.to_thread(
        sdk_client.create_repository,
        "e2e-sdk-repository",
        {"suite": "e2e"},
    )

    def run_workflow():
        with sdk_client.start_run(experiment.slug, dataset=ready_dataset, labels={"stage": "train"}) as run:
            run.log_metric("loss", 0.9, step=0)
            run.log_metrics({"loss": 0.4, "accuracy": 0.95}, step=1)
            return run.log_model(repository.slug, "e2e-sdk-model", "1.0", {"tree_depth": 4})

    logged_model = await asyncio.to_thread(run_workflow)
    downloaded_dataset = await asyncio.to_thread(
        sdk_client.download_dataset,
        ready_dataset.slug,
        ready_dataset.version,
    )
    downloaded_model = await asyncio.to_thread(
        sdk_client.download_model,
        repository.slug,
        logged_model.version,
        loader=lambda path: pickle.loads(path.read_bytes()),
    )
    run_info = await asyncio.to_thread(sdk_client.get_run, experiment.slug, 1)

    pdt.assert_frame_equal(downloaded_dataset, frame)
    assert downloaded_model == {"tree_depth": 4}
    assert logged_model.status == "READY"
    assert run_info.status == "COMPLETED"
    assert run_info.model.repository_slug == repository.slug
