from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://mlops:mlops@localhost:5433/mlops"
    test_database_url: str | None = None

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str | None = None
    minio_region: str = "us-east-1"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_use_ssl: bool = False
    minio_public_use_ssl: bool | None = None

    # Gitea
    gitea_url: str = "http://localhost:3002"
    gitea_admin_token: str = ""

    # Grafana
    grafana_url: str = "http://localhost:3001"
    grafana_public_url: str = "http://localhost:3001"
    grafana_admin_token: str = ""
    grafana_admin_user: str = "admin"
    grafana_admin_password: str = "admin"
    grafana_datasource_name: str = "mlops-postgres"
    grafana_datasource_host: str | None = None
    grafana_datasource_port: int | None = None
    grafana_datasource_database: str | None = None
    grafana_datasource_user: str | None = None
    grafana_datasource_password: str | None = None
    grafana_datasource_sslmode: str = "disable"

    # Security
    secret_key: str = "super-secret-dev-key-change-in-prod"
    access_token_lifetime_seconds: int = 3600

    # CORS
    cors_allowed_origins: list[str] = Field(default_factory=list)
    cors_allowed_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
