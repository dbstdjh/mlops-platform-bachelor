"""
Infrastructure adapter: MinIO storage.

Implements the StoragePort interface for pre-signed URL generation.
"""

from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from src.core.ports.storage import StoragePort


class MinioStorageAdapter(StoragePort):
    """MinIO implementation of the StoragePort."""

    def __init__(
        self,
        client: Minio,
        presign_client: Minio | None = None,
    ):
        self._client = client
        self._presign_client = presign_client or client

    async def generate_upload_url(self, bucket: str, object_name: str, expires_hours: int = 1) -> str:
        """Generate a pre-signed PUT URL for direct client upload to MinIO."""
        url = self._presign_client.presigned_put_object(
            bucket_name=bucket,
            object_name=object_name,
            expires=timedelta(hours=expires_hours),
        )
        return url

    async def generate_download_url(self, bucket: str, object_name: str, expires_hours: int = 1) -> str:
        """Generate a pre-signed GET URL for direct client download from MinIO."""
        url = self._presign_client.presigned_get_object(
            bucket_name=bucket,
            object_name=object_name,
            expires=timedelta(hours=expires_hours),
        )
        return url

    async def object_exists(self, bucket: str, object_name: str) -> bool:
        """Return whether the given object exists in MinIO."""
        try:
            self._client.stat_object(bucket_name=bucket, object_name=object_name)
        except S3Error:
            return False
        return True
