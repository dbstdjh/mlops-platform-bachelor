from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncio
import json
import uuid
import asyncpg


@dataclass(frozen=True)
class DeploymentTask:
    id: str
    deployment_id: str
    type: str


@dataclass(frozen=True)
class DeploymentSpec:
    deployment_id: str
    user_id: str
    deployment_slug: str
    source_type: str
    model_s3_uri: str | None = None
    model_file_type: str | None = None
    image_ref: str | None = None
    registry_username: str | None = None
    registry_host: str | None = None
    encrypted_registry_token: str | None = None


class DeploymentDatabase:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, database_url: str) -> "DeploymentDatabase":
        return cls(await asyncpg.create_pool(database_url))

    async def close(self) -> None:
        await self._pool.close()

    async def ensure_deployment_statuses(self) -> None:
        async with self._pool.acquire() as conn:
            for status in ("PENDING", "DEPLOYING", "ACTIVE", "FAILED", "DELETING", "DELETED"):
                await conn.execute(
                    """
                    INSERT INTO deployment_status (id, name)
                    VALUES ($1, $2)
                    ON CONFLICT (name) DO NOTHING
                    """,
                    uuid.uuid4(),
                    status,
                )

    async def claim_next_task(self) -> DeploymentTask | None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id, deployment_id, type
                    FROM deployment_task
                    WHERE status = 'PENDING'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                if row is None:
                    return None
                await conn.execute(
                    """
                    UPDATE deployment_task
                    SET status = 'IN_PROGRESS', claimed_at = NOW(), error_message = NULL
                    WHERE id = $1
                    """,
                    row["id"],
                )
                return DeploymentTask(
                    id=str(row["id"]),
                    deployment_id=str(row["deployment_id"]),
                    type=row["type"],
                )

    async def fetch_deployment_spec(self, deployment_id: str) -> DeploymentSpec:
        row = await self._pool.fetchrow(
            """
            SELECT
              d.id AS deployment_id,
              d.user_id AS user_id,
              d.slug AS deployment_slug,
              m.s3_uri AS model_s3_uri,
              ft.name AS model_file_type,
              idp.image_tag AS image_ref,
              ufc.config_data AS registry_config
            FROM deployment d
            LEFT JOIN file_deployment fd ON fd.id = d.id
            LEFT JOIN model m ON m.id = fd.model_id
            LEFT JOIN file_type ft ON ft.id = m.file_type_id
            LEFT JOIN image_deployment idp ON idp.id = d.id
            LEFT JOIN feature f ON f.name = 'custom_deployments'
            LEFT JOIN user_feature_config ufc ON ufc.feature_id = f.id AND ufc.user_id = d.user_id
            WHERE d.id = $1::uuid
            """,
            deployment_id,
        )
        if row is None:
            raise ValueError(f"Deployment '{deployment_id}' not found")
        source_type = "image" if row["image_ref"] else "file"
        if source_type == "file" and not row["model_s3_uri"]:
            raise ValueError("Deployment model does not have an artifact URI")
        registry_config = _decode_config(row["registry_config"])
        return DeploymentSpec(
            deployment_id=str(row["deployment_id"]),
            user_id=str(row["user_id"]),
            deployment_slug=row["deployment_slug"],
            source_type=source_type,
            model_s3_uri=row["model_s3_uri"],
            model_file_type=row["model_file_type"],
            image_ref=row["image_ref"],
            registry_username=registry_config.get("username"),
            registry_host=registry_config.get("registry_host"),
            encrypted_registry_token=registry_config.get("encrypted_proxy_token"),
        )

    async def mark_deployment_status(self, deployment_id: str, status: str) -> None:
        await self._pool.execute(
            """
            UPDATE deployment
            SET status_id = (
                SELECT id FROM deployment_status WHERE name = $2
            )
            WHERE id = $1::uuid
            """,
            deployment_id,
            status,
        )

    async def mark_deployment_active(
        self,
        deployment_id: str,
        *,
        endpoint_url: str,
        namespace: str,
        k8s_deployment_name: str,
        k8s_service_name: str,
        k8s_service_port: int,
    ) -> None:
        await self._pool.execute(
            """
            UPDATE deployment
            SET
              status_id = (SELECT id FROM deployment_status WHERE name = 'ACTIVE'),
              endpoint_url = $2,
              k8s_namespace = $3,
              k8s_deployment_name = $4,
              k8s_service_name = $5,
              k8s_service_port = $6
            WHERE id = $1::uuid
            """,
            deployment_id,
            endpoint_url,
            namespace,
            k8s_deployment_name,
            k8s_service_name,
            k8s_service_port,
        )

    async def mark_task_completed(self, task_id: str) -> None:
        await self._pool.execute(
            """
            UPDATE deployment_task
            SET status = 'COMPLETED', completed_at = NOW(), error_message = NULL
            WHERE id = $1::uuid
            """,
            task_id,
        )

    async def mark_task_failed(self, task_id: str, error_message: str) -> None:
        await self._pool.execute(
            """
            UPDATE deployment_task
            SET status = 'FAILED', completed_at = NOW(), error_message = $2
            WHERE id = $1::uuid
            """,
            task_id,
            error_message[:1000],
        )

    async def listen(self, channel: str):
        queue: asyncio.Queue[str] = asyncio.Queue()

        def callback(*args: Any) -> None:
            queue.put_nowait(args[3])

        conn = await self._pool.acquire()
        await conn.add_listener(channel, callback)
        try:
            while True:
                yield await queue.get()
        finally:
            await conn.remove_listener(channel, callback)
            await self._pool.release(conn)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decode_config(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)
