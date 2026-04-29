"""
Core domain entity: API Key

User-managed API keys can be exchanged for JWTs.
The plaintext secret is shown exactly once on creation.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ApiKey(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    name: str
    prefix: str
    hashed_key: str
    is_revoked: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyResponse(BaseModel):
    name: str
    prefix: str
    is_revoked: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyIssuedResponse(ApiKeyResponse):
    api_key: str


class UserLogin(BaseModel):
    email: str
    password: str


class ApiKeyExchangeRequest(BaseModel):
    email: str
    api_key: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
