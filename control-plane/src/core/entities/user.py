from datetime import datetime

from fastapi_users import schemas
from pydantic import ConfigDict, EmailStr, Field


class UserRead(schemas.CreateUpdateDictModel):
    model_config = ConfigDict(from_attributes=True)

    email: EmailStr
    is_active: bool
    is_superuser: bool
    is_verified: bool
    created_at: datetime


class UserCreate(schemas.CreateUpdateDictModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserUpdate(schemas.CreateUpdateDictModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8)
