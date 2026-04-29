from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_users import exceptions, schemas

from src.application.api_key_service import ApiKeyService
from src.core.entities.api_key import (
    AccessTokenResponse,
    ApiKeyCreate,
    ApiKeyExchangeRequest,
    ApiKeyIssuedResponse,
    ApiKeyResponse,
    UserLogin,
)
from src.core.entities.user import UserCreate, UserRead, UserUpdate
from src.infrastructure.auth.fastapi_users import (
    UserManager,
    get_jwt_strategy,
    get_user_manager,
)
from src.infrastructure.database.models import UserORM
from src.presentation.dependencies import get_api_key_service, get_current_user

router = APIRouter()


@router.post("/users:register", response_model=UserRead, status_code=201)
async def register(
    data: UserCreate,
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
):
    """Register a user as active, non-superuser, and verified for Phase 1."""
    create_data = schemas.BaseUserCreate(
        email=data.email,
        password=data.password,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    try:
        return await user_manager.create(create_data, safe=False, request=request)
    except exceptions.UserAlreadyExists as exc:
        raise HTTPException(status_code=400, detail="User already exists") from exc


@router.post("/users:login", response_model=AccessTokenResponse)
async def login(
    data: UserLogin,
    user_manager: UserManager = Depends(get_user_manager),
):
    """Authenticate with email/password and return a JWT bearer token."""
    user = await user_manager.authenticate_credentials(data.email, data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )

    token = await get_jwt_strategy().write_token(user)
    return AccessTokenResponse(access_token=token)


@router.get("/users/me", response_model=UserRead)
async def get_me(
    user: UserORM = Depends(get_current_user),
):
    """Return the current authenticated user's profile."""
    return user


@router.patch("/users/me", response_model=UserRead)
async def update_me(
    data: UserUpdate,
    request: Request,
    user: UserORM = Depends(get_current_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Update the current authenticated user's profile."""
    return await user_manager.update(data, user, safe=True, request=request)


@router.get("/users/me/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: UserORM = Depends(get_current_user),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """List the current user's API keys without exposing the plaintext secrets."""
    return await service.list_keys(user.id)


@router.post("/users/me/api-keys", response_model=ApiKeyIssuedResponse, status_code=201)
async def create_api_key(
    data: ApiKeyCreate,
    user: UserORM = Depends(get_current_user),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """Create a new API key and return the plaintext secret exactly once."""
    try:
        return await service.issue_key(user.id, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/users/me/api-keys/{key_name}:revoke", status_code=200)
async def revoke_api_key(
    key_name: str,
    user: UserORM = Depends(get_current_user),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """Revoke an existing API key by its user-facing name."""
    revoked = await service.revoke_key(user.id, key_name)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "ok"}


@router.post("/users:login_with_api_key", response_model=AccessTokenResponse)
async def exchange_api_key_for_jwt(
    data: ApiKeyExchangeRequest,
    user_manager: UserManager = Depends(get_user_manager),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """Exchange email plus API key for a short-lived JWT bearer token."""
    try:
        user = await user_manager.get_by_email(data.email)
    except exceptions.UserNotExists as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc

    is_valid = await service.authenticate_for_user(user.id, data.api_key)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )

    token = await get_jwt_strategy().write_token(user)
    return service.build_access_token_response(token)
