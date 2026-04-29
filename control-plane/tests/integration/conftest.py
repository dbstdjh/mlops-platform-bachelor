import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.support.database import isolated_test_app


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_app():
    async with isolated_test_app() as (app, _session_factory):
        yield app


@pytest_asyncio.fixture
async def anonymous_client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def client(anonymous_client):
    email = f"integration-user-{uuid.uuid4().hex}@example.com"
    await anonymous_client.post(
        "/api/v1/users:register",
        json={
            "email": email,
            "password": "IntegrationPass123",
        },
    )
    login_response = await anonymous_client.post(
        "/api/v1/users:login",
        json={
            "email": email,
            "password": "IntegrationPass123",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    anonymous_client.headers["Authorization"] = f"Bearer {token}"
    yield anonymous_client
