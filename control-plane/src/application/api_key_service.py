"""
Application service: User API keys.

Manages creation, listing, revocation, and authentication of user API keys.
"""

import hashlib
import hmac
import secrets
import uuid

from src.core.entities.api_key import (
    AccessTokenResponse,
    ApiKey,
    ApiKeyCreate,
    ApiKeyIssuedResponse,
    ApiKeyResponse,
)
from src.core.ports.repositories import ApiKeyRepo


class ApiKeyService:
    KEY_PREFIX = "mlp"

    def __init__(self, api_key_repo: ApiKeyRepo):
        self._api_key_repo = api_key_repo

    async def issue_key(self, user_id: uuid.UUID, data: ApiKeyCreate) -> ApiKeyIssuedResponse:
        if await self._api_key_repo.name_exists(user_id, data.name):
            raise ValueError(f"API key '{data.name}' already exists")

        prefix = await self._generate_unique_prefix()
        secret = secrets.token_hex(32)
        raw_key = self._format_key(prefix, secret)

        api_key = ApiKey(
            user_id=user_id,
            name=data.name,
            prefix=prefix,
            hashed_key=self._hash_key(raw_key),
        )
        await self._api_key_repo.create(api_key)

        return ApiKeyIssuedResponse(
            name=api_key.name,
            prefix=api_key.prefix,
            is_revoked=api_key.is_revoked,
            created_at=api_key.created_at,
            api_key=raw_key,
        )

    async def list_keys(self, user_id: uuid.UUID) -> list[ApiKeyResponse]:
        keys = await self._api_key_repo.list_by_user(user_id)
        return [
            ApiKeyResponse(
                name=key.name,
                prefix=key.prefix,
                is_revoked=key.is_revoked,
                created_at=key.created_at,
            )
            for key in keys
        ]

    async def revoke_key(self, user_id: uuid.UUID, name: str) -> bool:
        return await self._api_key_repo.revoke(user_id, name)

    async def authenticate_for_user(self, user_id: uuid.UUID, raw_key: str) -> bool:
        prefix = self._extract_prefix(raw_key)
        if not prefix:
            return False

        api_key = await self._api_key_repo.get_by_prefix(prefix)
        if not api_key or api_key.is_revoked:
            return False
        if api_key.user_id != user_id:
            return False

        expected_hash = self._hash_key(raw_key)
        if not hmac.compare_digest(expected_hash, api_key.hashed_key):
            return False

        return True

    def build_access_token_response(self, access_token: str) -> AccessTokenResponse:
        return AccessTokenResponse(access_token=access_token)

    async def _generate_unique_prefix(self) -> str:
        while True:
            prefix = secrets.token_hex(6)
            if not await self._api_key_repo.prefix_exists(prefix):
                return prefix

    def _format_key(self, prefix: str, secret: str) -> str:
        return f"{self.KEY_PREFIX}_{prefix}_{secret}"

    def _extract_prefix(self, raw_key: str) -> str | None:
        parts = raw_key.split("_", 2)
        if len(parts) != 3 or parts[0] != self.KEY_PREFIX or not parts[1] or not parts[2]:
            return None
        return parts[1]

    def _hash_key(self, raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
