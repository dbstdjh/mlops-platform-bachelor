import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
from fastapi_users.authentication import JWTStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.core.entities.user import UserCreate, UserUpdate
from src.infrastructure.database.models import UserORM
from src.infrastructure.database.session import get_db

bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="Paste a JWT access token in the form 'Bearer <token>'.",
    auto_error=False,
)


def get_jwt_strategy() -> JWTStrategy:
    settings = get_settings()
    return JWTStrategy(
        secret=settings.secret_key,
        lifetime_seconds=settings.access_token_lifetime_seconds,
    )


async def get_user_db(
    session: AsyncSession = Depends(get_db),
) -> AsyncIterator[SQLAlchemyUserDatabase[UserORM, uuid.UUID]]:
    yield SQLAlchemyUserDatabase(session, UserORM)


class UserManager(UUIDIDMixin, BaseUserManager[UserORM, uuid.UUID]):
    def __init__(
        self,
        user_db: SQLAlchemyUserDatabase[UserORM, uuid.UUID],
        settings: Settings,
    ) -> None:
        super().__init__(user_db)
        self.reset_password_token_secret = settings.secret_key
        self.verification_token_secret = settings.secret_key

    async def validate_password(
        self,
        password: str,
        user: UserCreate | UserUpdate | UserORM,
    ) -> None:
        if len(password) < 8:
            raise exceptions.InvalidPasswordException(
                reason="Password should be at least 8 characters",
            )

        if user.email.lower() in password.lower():
            raise exceptions.InvalidPasswordException(
                reason="Password should not contain e-mail",
            )

    async def authenticate_credentials(self, email: str, password: str) -> UserORM | None:
        try:
            user = await self.get_by_email(email)
        except exceptions.UserNotExists:
            self.password_helper.hash(password)
            return None

        verified, updated_password_hash = self.password_helper.verify_and_update(
            password,
            user.hashed_password,
        )
        if not verified:
            return None
        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})

        return user


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[UserORM, uuid.UUID] = Depends(get_user_db),
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[UserManager]:
    yield UserManager(user_db, settings)


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    user_manager: UserManager = Depends(get_user_manager),
) -> UserORM | None:
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    return await get_jwt_strategy().read_token(token, user_manager)


async def get_current_active_user(
    user: UserORM | None = Depends(get_optional_current_user),
) -> UserORM:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )
    return user
