from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://mldlc:change-me@db:5432/mldlc"
    listen_channel: str = "deployment_tasks"

    namespace: str = "mldlc"
    model_service_type: str = "ClusterIP"
    gateway_public_url: str = "http://gateway.mldlc.local"
    prebuilt_pickle_image: str = "mldlc/sklearn-pickle-server:dev"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    secret_key: str = "super-secret-dev-key-change-in-prod"

    poll_interval_seconds: float = 2.0
    rollout_timeout_seconds: float = 180.0
    endpoint_timeout_seconds: float = 180.0
    ready_timeout_seconds: float = 60.0

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def asyncpg_database_url(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
