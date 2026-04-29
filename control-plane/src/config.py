from pydantic_settings import BaseSettings
from functools import lru_cache


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
    grafana_admin_token: str = ""

    # Security
    secret_key: str = "super-secret-dev-key-change-in-prod"
    access_token_lifetime_seconds: int = 3600

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
