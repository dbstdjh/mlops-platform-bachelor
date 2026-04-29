from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from mldlc import MLDLC
from tests.support.database import isolated_test_app


class SyncAsyncClientAdapter:
    def __init__(self, async_client: AsyncClient, loop: asyncio.AbstractEventLoop) -> None:
        self._async_client = async_client
        self._loop = loop

    def request(self, method: str, url: str, **kwargs):
        future = asyncio.run_coroutine_threadsafe(
            self._async_client.request(method, url, **kwargs),
            self._loop,
        )
        return future.result()

    def post(self, url: str, **kwargs):
        future = asyncio.run_coroutine_threadsafe(
            self._async_client.post(url, **kwargs),
            self._loop,
        )
        return future.result()

    def close(self) -> None:
        return None


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_app():
    async with isolated_test_app() as (app, _session_factory):
        yield app


@pytest_asyncio.fixture
async def control_plane_client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def sdk_client(control_plane_client):
    email = f"sdk-e2e-{uuid.uuid4().hex}@example.com"
    password = "SdkPass123"

    register_response = await control_plane_client.post(
        "/api/v1/users:register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 201

    login_response = await control_plane_client.post(
        "/api/v1/users:login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    control_plane_client.headers["Authorization"] = f"Bearer {login_response.json()['access_token']}"

    api_key_response = await control_plane_client.post("/api/v1/users/me/api-keys", json={"name": "sdk"})
    assert api_key_response.status_code == 201
    api_key = api_key_response.json()["api_key"]

    loop = asyncio.get_running_loop()
    client = MLDLC(
        email,
        api_key,
        base_url="http://test",
        _control_plane_client=SyncAsyncClientAdapter(control_plane_client, loop),
        _artifact_client=httpx.Client(timeout=30.0, trust_env=False),
    )
    try:
        yield client
    finally:
        client.close()
