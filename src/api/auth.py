from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, require_admin
from src.api.schemas import RegisterRequest, TokenResponse, UserResponse
from src.database.connection import get_db
from src.models.user import User, UserRole
from src.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_user,
    get_user_by_email,
    hash_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
    responses={401: {"description": "Invalid credentials"}},
)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> TokenResponse:
    user = await authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": user.email})
    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
    responses={401: {"description": "Invalid or expired token"}},
)
async def me(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=current_user.role.value,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user (admin only)",
    responses={
        400: {"description": "Email already registered"},
        403: {"description": "Admin access required"},
    },
)
async def register(
    data: RegisterRequest,
    _admin: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> UserResponse:
    existing = await get_user_by_email(db, data.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    try:
        role = UserRole(data.role)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {data.role}",
        ) from err
    user = await create_user(
        session=db,
        email=data.email,
        hashed_password=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        role=role,
    )
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role.value,
    )
