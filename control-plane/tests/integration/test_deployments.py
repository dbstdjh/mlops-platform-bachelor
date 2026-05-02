import pickle
import asyncio

import asyncpg
import httpx
import pytest
from sqlalchemy import select

from src.infrastructure.database.models import DeploymentORM, DeploymentTaskORM


async def upload_bytes(url: str, payload: bytes) -> None:
    async with httpx.AsyncClient(trust_env=False) as storage_client:
        response = await storage_client.put(url, content=payload, headers={"content-type": "application/octet-stream"})
    assert response.status_code in {200, 201, 204}


@pytest.mark.asyncio
async def test_create_deployment_inserts_file_deployment_task_and_emits_notify(client, test_app):
    repo_resp = await client.post("/api/v1/repositories", json={"name": "deploy-repo"})
    repo_slug = repo_resp.json()["slug"]
    await client.post(
        f"/api/v1/repositories/{repo_slug}/models",
        json={"name": "classifier", "version": "1.0"},
    )
    upload_resp = await client.post(
        f"/api/v1/repositories/{repo_slug}/models/1.0:upload",
        json={"file_name": "classifier.pkl"},
    )
    upload_url = upload_resp.json()["upload_url"]
    await upload_bytes(upload_url, pickle.dumps({"model": "deployment"}))
    object_key = upload_url.split("/models/", maxsplit=1)[1].split("?", maxsplit=1)[0]
    await client.post(
        "/api/v1/models:confirm_upload",
        json={"Records": [{"s3": {"object": {"key": object_key}}}]},
    )

    database_url = test_app.state.db_engine.url.render_as_string(hide_password=False)
    listen_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    notify_queue = asyncio.Queue()
    listen_conn = await asyncpg.connect(listen_url)
    await listen_conn.add_listener(
        "deployment_tasks",
        lambda _conn, _pid, _channel, payload: notify_queue.put_nowait(payload),
    )
    try:
        response = await client.post(
            f"/api/v1/repositories/{repo_slug}/models/1.0/deployments",
            json={"name": "Fraud Prod", "input_schema": {"type": "object"}},
        )
        assert response.status_code == 201
        assert response.json()["slug"] == "fraud-prod"
        assert "id" not in response.json()

        assert await asyncio.wait_for(notify_queue.get(), timeout=2.0) == ""
    finally:
        await listen_conn.close()

    session_factory = test_app.state.db_session_factory
    async with session_factory() as session:
        deployment = (
            await session.execute(select(DeploymentORM).where(DeploymentORM.slug == "fraud-prod"))
        ).scalar_one()
        task = (
            await session.execute(select(DeploymentTaskORM).where(DeploymentTaskORM.deployment_id == deployment.id))
        ).scalar_one()
        assert task.type == "DEPLOY"
        assert task.status == "PENDING"
