from types import SimpleNamespace

import pytest
from fastapi_users.exceptions import InvalidPasswordException

from src.config import Settings
from src.infrastructure.auth.fastapi_users import UserManager, get_jwt_strategy


def test_get_jwt_strategy_uses_settings(monkeypatch):
    monkeypatch.setattr(
        "src.infrastructure.auth.fastapi_users.get_settings",
        lambda: Settings(
            secret_key="jwt-secret",
            access_token_lifetime_seconds=7200,
        ),
    )

    strategy = get_jwt_strategy()

    assert strategy.secret == "jwt-secret"
    assert strategy.lifetime_seconds == 7200


@pytest.mark.asyncio
async def test_user_manager_rejects_short_password():
    manager = UserManager(SimpleNamespace(), Settings(secret_key="secret"))

    with pytest.raises(InvalidPasswordException) as exc_info:
        await manager.validate_password(
            "short",
            SimpleNamespace(email="user@example.com"),
        )

    assert exc_info.value.reason == "Password should be at least 8 characters"


@pytest.mark.asyncio
async def test_user_manager_rejects_password_containing_email():
    manager = UserManager(SimpleNamespace(), Settings(secret_key="secret"))

    with pytest.raises(InvalidPasswordException) as exc_info:
        await manager.validate_password(
            "user@example.com-very-secret",
            SimpleNamespace(email="user@example.com"),
        )

    assert exc_info.value.reason == "Password should not contain e-mail"


@pytest.mark.asyncio
async def test_user_manager_accepts_strong_password():
    manager = UserManager(SimpleNamespace(), Settings(secret_key="secret"))

    await manager.validate_password(
        "StrongPass123",
        SimpleNamespace(email="user@example.com"),
    )
