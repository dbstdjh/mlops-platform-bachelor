"""Gitea Artifact Registry HTTP adapter."""

from datetime import datetime
from typing import Any

import httpx

from src.core.entities.artifact_registry import ArtifactImage, ArtifactImageTag, RegistryTokenResponse
from src.core.ports.artifact_registry import GiteaRegistryClient


class GiteaRegistryError(RuntimeError):
    """Raised when Gitea rejects a registry operation."""


class HttpGiteaRegistryClient(GiteaRegistryClient):
    """HTTP adapter for Gitea user tokens and container packages."""

    def __init__(self, *, base_url: str, admin_token: str, http_client: httpx.AsyncClient):
        self._base_url = base_url.rstrip("/")
        self._admin_token = admin_token
        self._http = http_client

    async def ensure_user(self, username: str, email: str, password: str) -> None:
        response = await self._request("GET", f"/users/{username}", admin=True, expected=(200, 404))
        if response.status_code == 404:
            await self._request(
                "POST",
                "/admin/users",
                admin=True,
                json={
                    "username": username,
                    "email": email,
                    "password": password,
                    "must_change_password": False,
                    "send_notify": False,
                    "restricted": False,
                },
                expected=(201, 422),
            )
            return
        await self.reset_user_password(username, password)

    async def reset_user_password(self, username: str, password: str) -> None:
        await self._request(
            "PATCH",
            f"/admin/users/{username}",
            admin=True,
            json={
                "source_id": 0,
                "login_name": username,
                "password": password,
                "must_change_password": False,
                "prohibit_login": False,
            },
            expected=(200, 204),
        )

    async def create_token_with_password(
        self,
        username: str,
        password: str,
        *,
        name: str,
        scopes: list[str],
    ) -> tuple[str, RegistryTokenResponse]:
        response = await self._request(
            "POST",
            f"/users/{username}/tokens",
            auth=(username, password),
            json={"name": name, "scopes": scopes},
            expected=(200, 201),
        )
        payload = response.json()
        token = str(payload.get("sha1") or payload.get("token") or "")
        if not token:
            raise GiteaRegistryError("Gitea did not return a plaintext token")
        return token, self._token_from_payload(payload, fallback_name=name)

    async def revoke_token_with_password(self, username: str, password: str, name: str) -> bool:
        response = await self._request(
            "DELETE",
            f"/users/{username}/tokens/{name}",
            auth=(username, password),
            expected=(204, 404),
        )
        return response.status_code == 204

    async def list_container_images(self, username: str, token: str, registry_host: str) -> list[ArtifactImage]:
        response = await self._request(
            "GET",
            f"/packages/{username}",
            token=token,
            params={"type": "container", "limit": 100},
        )
        images: list[ArtifactImage] = []
        for package in response.json():
            name = str(package.get("name") or "")
            if not name or "/" in name:
                continue
            version_response = await self._request(
                "GET",
                f"/packages/{username}/container/{name}",
                token=token,
                params={"limit": 100},
            )
            tags = [
                ArtifactImageTag(
                    tag=str(version.get("version") or version.get("name")),
                    image_ref=f"{registry_host}/{username}/{name}:{version.get('version') or version.get('name')}",
                    created_at=self._parse_datetime(version.get("created_at")),
                )
                for version in version_response.json()
                if version.get("version") or version.get("name")
            ]
            images.append(ArtifactImage(name=name, tags=tags))
        return images

    async def image_tag_exists(self, username: str, token: str, image_name: str, tag: str) -> bool:
        response = await self._request(
            "GET",
            f"/packages/{username}/container/{image_name}/{tag}",
            token=token,
            expected=(200, 404),
        )
        return response.status_code == 200

    async def _request(
        self,
        method: str,
        path: str,
        *,
        admin: bool = False,
        token: str | None = None,
        auth: tuple[str, str] | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if admin:
            if not self._admin_token:
                raise GiteaRegistryError("Gitea admin token is not configured")
            headers["Authorization"] = f"token {self._admin_token}"
        if token:
            headers["Authorization"] = f"token {token}"

        response = await self._http.request(
            method,
            f"{self._base_url}/api/v1{path}",
            headers=headers,
            auth=auth,
            json=json,
            params=params,
        )
        if response.status_code not in expected:
            raise GiteaRegistryError(self._error_detail(response))
        return response

    def _token_from_payload(self, payload: dict[str, Any], fallback_name: str | None = None) -> RegistryTokenResponse:
        return RegistryTokenResponse(
            name=str(payload.get("name") or fallback_name or ""),
            token_last_eight=payload.get("token_last_eight"),
            created_at=self._parse_datetime(payload.get("created_at")),
        )

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _error_detail(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or f"Gitea request failed with status {response.status_code}"
        if isinstance(payload, dict) and payload.get("message"):
            return str(payload["message"])
        return f"Gitea request failed with status {response.status_code}"
