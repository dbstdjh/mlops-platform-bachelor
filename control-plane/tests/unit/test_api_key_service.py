import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.api_key_service import ApiKeyService
from src.core.entities.api_key import ApiKey, ApiKeyCreate


@pytest.mark.asyncio
async def test_issue_key_persists_hashed_key_and_returns_plaintext(monkeypatch):
    repo = SimpleNamespace(
        create=AsyncMock(),
        name_exists=AsyncMock(return_value=False),
        prefix_exists=AsyncMock(return_value=False),
    )
    service = ApiKeyService(repo)
    user_id = uuid.uuid4()

    async def fixed_prefix():
        return "abc123def456"

    monkeypatch.setattr(service, "_generate_unique_prefix", fixed_prefix)
    monkeypatch.setattr("src.application.api_key_service.secrets.token_hex", lambda _n: "f" * 64)

    response = await service.issue_key(user_id, ApiKeyCreate(name="sdk"))

    assert response.name == "sdk"
    assert response.api_key == "mlp_abc123def456_" + ("f" * 64)
    persisted = repo.create.await_args.args[0]
    assert persisted.user_id == user_id
    assert persisted.prefix == "abc123def456"
    assert persisted.hashed_key != response.api_key


@pytest.mark.asyncio
async def test_list_keys_maps_entities_to_safe_response_models():
    created_at = datetime.now(timezone.utc)
    repo = SimpleNamespace(
        list_by_user=AsyncMock(
            return_value=[
                ApiKey(
                    user_id=uuid.uuid4(),
                    name="cli",
                    prefix="abc123",
                    hashed_key="hashed",
                    is_revoked=False,
                    created_at=created_at,
                )
            ]
        )
    )
    service = ApiKeyService(repo)

    result = await service.list_keys(uuid.uuid4())

    assert len(result) == 1
    assert result[0].name == "cli"
    assert result[0].prefix == "abc123"
    assert result[0].is_revoked is False
    assert result[0].created_at == created_at


@pytest.mark.asyncio
async def test_revoke_key_delegates_to_repository():
    repo = SimpleNamespace(revoke=AsyncMock(return_value=True))
    service = ApiKeyService(repo)
    user_id = uuid.uuid4()

    result = await service.revoke_key(user_id, "abc123")

    assert result is True
    repo.revoke.assert_awaited_once_with(user_id, "abc123")


@pytest.mark.asyncio
async def test_authenticate_returns_user_id_for_valid_key():
    user_id = uuid.uuid4()
    raw_key = "mlp_abc123_secret"
    helper = ApiKeyService(SimpleNamespace())
    repo = SimpleNamespace(
        get_by_prefix=AsyncMock(
            return_value=ApiKey(
                user_id=user_id,
                name="cli",
                prefix="abc123",
                hashed_key=helper._hash_key(raw_key),
                is_revoked=False,
            )
        )
    )
    service = ApiKeyService(repo)

    result = await service.authenticate_for_user(user_id, raw_key)

    assert result is True


@pytest.mark.asyncio
async def test_authenticate_rejects_invalid_or_revoked_keys():
    other_user_id = uuid.uuid4()
    repo = SimpleNamespace(
        get_by_prefix=AsyncMock(
            side_effect=[
                None,
                ApiKey(
                    user_id=other_user_id,
                    name="cli",
                    prefix="abc123",
                    hashed_key="hashed",
                    is_revoked=True,
                ),
                ApiKey(
                    user_id=other_user_id,
                    name="cli",
                    prefix="abc123",
                    hashed_key="different",
                    is_revoked=False,
                ),
                ApiKey(
                    user_id=other_user_id,
                    name="cli",
                    prefix="abc123",
                    hashed_key=ApiKeyService(SimpleNamespace())._hash_key("mlp_abc123_secret"),
                    is_revoked=False,
                ),
            ]
        )
    )
    service = ApiKeyService(repo)
    target_user_id = uuid.uuid4()

    assert await service.authenticate_for_user(target_user_id, "malformed") is False
    assert await service.authenticate_for_user(target_user_id, "mlp_abc123_secret") is False
    assert await service.authenticate_for_user(target_user_id, "mlp_abc123_secret") is False
    assert await service.authenticate_for_user(target_user_id, "mlp_abc123_secret") is False
    assert await service.authenticate_for_user(target_user_id, "mlp_abc123_secret") is False
