from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.presentation.api.v1 import users
from src.presentation.dependencies import get_api_key_service
from src.presentation.dependencies import get_current_user
from src.infrastructure.auth.fastapi_users import get_user_manager


def create_user_test_app(user, user_manager, api_key_service=None):
    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_user_manager] = lambda: user_manager
    if api_key_service is not None:
        app.dependency_overrides[get_api_key_service] = lambda: api_key_service
    return app


def build_user():
    return SimpleNamespace(
        id="user-id",
        email="user@example.com",
        is_active=True,
        is_superuser=False,
        is_verified=False,
        created_at="2026-01-01T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_get_me_returns_current_user_profile():
    user = build_user()
    app = create_user_test_app(user, SimpleNamespace())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_update_me_uses_user_manager_with_safe_mode():
    user = build_user()
    updated_user = SimpleNamespace(
        email="updated@example.com",
        is_active=True,
        is_superuser=False,
        is_verified=False,
        created_at="2026-01-01T00:00:00Z",
    )
    user_manager = SimpleNamespace(update=AsyncMock(return_value=updated_user))
    app = create_user_test_app(user, user_manager)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"email": "updated@example.com"},
        )

    assert response.status_code == 200
    assert response.json()["email"] == "updated@example.com"
    assert user_manager.update.await_args.kwargs["safe"] is True


@pytest.mark.asyncio
async def test_list_api_keys_returns_safe_payload():
    user = build_user()
    api_key_service = SimpleNamespace(
        list_keys=AsyncMock(
            return_value=[
                {
                    "name": "sdk",
                    "prefix": "abc123",
                    "is_revoked": False,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        )
    )
    app = create_user_test_app(user, SimpleNamespace(), api_key_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/users/me/api-keys")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "sdk"
    assert response.json()[0]["prefix"] == "abc123"


@pytest.mark.asyncio
async def test_create_api_key_returns_plaintext_once():
    user = build_user()
    api_key_service = SimpleNamespace(
        issue_key=AsyncMock(
                return_value={
                    "name": "sdk",
                    "prefix": "abc123",
                    "is_revoked": False,
                    "created_at": "2026-01-01T00:00:00Z",
                    "api_key": "mlp_abc123_secret",
                }
            )
    )
    app = create_user_test_app(user, SimpleNamespace(), api_key_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/users/me/api-keys", json={"name": "sdk"})

    assert response.status_code == 201
    assert response.json()["api_key"] == "mlp_abc123_secret"
    assert response.json()["prefix"] == "abc123"


@pytest.mark.asyncio
async def test_revoke_api_key_returns_404_when_missing():
    user = build_user()
    api_key_service = SimpleNamespace(revoke_key=AsyncMock(return_value=False))
    app = create_user_test_app(user, SimpleNamespace(), api_key_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/users/me/api-keys/sdk:revoke")

    assert response.status_code == 404
    assert response.json()["detail"] == "API key not found"


@pytest.mark.asyncio
async def test_exchange_api_key_returns_jwt(monkeypatch):
    async def write_token(_user):
        return "jwt-token"

    monkeypatch.setattr(users, "get_jwt_strategy", lambda: SimpleNamespace(write_token=write_token))
    user_manager = SimpleNamespace(
        update=AsyncMock(),
        get_by_email=AsyncMock(return_value=SimpleNamespace(id="user-id", is_active=True)),
    )
    api_key_service = SimpleNamespace(
        authenticate_for_user=AsyncMock(return_value=True),
        build_access_token_response=lambda token: {"access_token": token, "token_type": "bearer"},
    )
    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1")
    app.dependency_overrides[get_user_manager] = lambda: user_manager
    app.dependency_overrides[get_api_key_service] = lambda: api_key_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/users:login_with_api_key",
            json={"email": "user@example.com", "api_key": "mlp_abc123_secret"},
        )

    assert response.status_code == 200
    assert response.json()["access_token"] == "jwt-token"


@pytest.mark.asyncio
async def test_exchange_api_key_returns_401_for_invalid_key():
    user_manager = SimpleNamespace(
        update=AsyncMock(),
        get_by_email=AsyncMock(return_value=SimpleNamespace(id="user-id", is_active=True)),
    )
    api_key_service = SimpleNamespace(authenticate_for_user=AsyncMock(return_value=False))
    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1")
    app.dependency_overrides[get_user_manager] = lambda: user_manager
    app.dependency_overrides[get_api_key_service] = lambda: api_key_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/users:login_with_api_key",
            json={"email": "user@example.com", "api_key": "bad"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
