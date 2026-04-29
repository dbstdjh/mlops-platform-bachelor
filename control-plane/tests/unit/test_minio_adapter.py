from datetime import timedelta
from unittest.mock import Mock

import pytest

from src.infrastructure.storage.minio_adapter import MinioStorageAdapter


@pytest.mark.asyncio
async def test_generate_upload_url_uses_injected_minio_client():
    client = Mock()
    client.presigned_put_object.return_value = "https://upload.test/datasets/object"
    adapter = MinioStorageAdapter(client)

    result = await adapter.generate_upload_url("datasets", "user/object.csv", expires_hours=3)

    assert result == "https://upload.test/datasets/object"
    client.presigned_put_object.assert_called_once_with(
        bucket_name="datasets",
        object_name="user/object.csv",
        expires=timedelta(hours=3),
    )


@pytest.mark.asyncio
async def test_generate_download_url_uses_injected_minio_client():
    client = Mock()
    client.presigned_get_object.return_value = "https://download.test/datasets/object"
    adapter = MinioStorageAdapter(client)

    result = await adapter.generate_download_url("datasets", "user/object.csv", expires_hours=2)

    assert result == "https://download.test/datasets/object"
    client.presigned_get_object.assert_called_once_with(
        bucket_name="datasets",
        object_name="user/object.csv",
        expires=timedelta(hours=2),
    )


@pytest.mark.asyncio
async def test_generate_upload_url_uses_presign_client_when_provided():
    client = Mock()
    presign_client = Mock()
    presign_client.presigned_put_object.return_value = "http://localhost:9000/datasets/object?signature=abc"
    adapter = MinioStorageAdapter(client, presign_client=presign_client)

    result = await adapter.generate_upload_url("datasets", "user/object.csv", expires_hours=1)

    assert result == "http://localhost:9000/datasets/object?signature=abc"
    presign_client.presigned_put_object.assert_called_once()
    client.presigned_put_object.assert_not_called()


@pytest.mark.asyncio
async def test_generate_download_url_uses_presign_client_when_provided():
    client = Mock()
    presign_client = Mock()
    presign_client.presigned_get_object.return_value = "http://127.0.0.1:9000/datasets/object?signature=abc"
    adapter = MinioStorageAdapter(client, presign_client=presign_client)

    result = await adapter.generate_download_url("datasets", "user/object.csv", expires_hours=1)

    assert result == "http://127.0.0.1:9000/datasets/object?signature=abc"
    presign_client.presigned_get_object.assert_called_once()
    client.presigned_get_object.assert_not_called()


@pytest.mark.asyncio
async def test_object_exists_uses_injected_minio_client():
    client = Mock()
    adapter = MinioStorageAdapter(client)

    result = await adapter.object_exists("datasets", "user/object.csv")

    assert result is True
    client.stat_object.assert_called_once_with(
        bucket_name="datasets",
        object_name="user/object.csv",
    )
