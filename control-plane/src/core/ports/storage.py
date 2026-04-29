"""
Core port: Storage interface.

Defines the contract for object storage operations (MinIO).
"""

from abc import ABC, abstractmethod


class StoragePort(ABC):
    """Port for object storage interactions (pre-signed URLs, etc.)."""

    @abstractmethod
    async def generate_upload_url(self, bucket: str, object_name: str, expires_hours: int = 1) -> str:
        """Generate a pre-signed PUT URL for direct client upload."""
        ...

    @abstractmethod
    async def generate_download_url(self, bucket: str, object_name: str, expires_hours: int = 1) -> str:
        """Generate a pre-signed GET URL for direct client download."""
        ...

    @abstractmethod
    async def object_exists(self, bucket: str, object_name: str) -> bool:
        """Return whether the given object is present in storage."""
        ...
