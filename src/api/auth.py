from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, require_admin
from src.api.schemas import (
    RegisterRequest,
    TokenResponse,
    UserISICUpdateRequest,
    UserResponse,
    UserUpdateRequest,
)
from src.database.connection import get_db
from src.models.user import User, UserRole
from src.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    list_users_by_role,
    update_user,
    update_user_isic_identifier,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_teacher_isic(isic_identifier: str | None) -> str:
    if isic_identifier is None or not isic_identifier.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ISIC identifier is required for teachers",
        )
    return isic_identifier


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
        isic_identifier=current_user.isic_identifier,
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

    isic_identifier = (
        _require_teacher_isic(data.isic_identifier)
        if role == UserRole.teacher
        else data.isic_identifier
    )

    try:
        user = await create_user(
            session=db,
            email=data.email,
            hashed_password=hash_password(data.password),
            isic_identifier=isic_identifier,
            first_name=data.first_name,
            last_name=data.last_name,
            role=role,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ISIC identifier already used",
        ) from err
    return UserResponse(
        id=user.id,
        email=user.email,
        isic_identifier=user.isic_identifier,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role.value,
    )


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        isic_identifier=user.isic_identifier,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role.value,
    )


@router.get(
    "/teachers",
    response_model=list[UserResponse],
    summary="List all teachers (admin only)",
    responses={403: {"description": "Admin access required"}},
)
async def list_teachers(
    _admin: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[UserResponse]:
    teachers = await list_users_by_role(db, UserRole.teacher)
    return [_user_to_response(teacher) for teacher in teachers]


@router.patch(
    "/teachers/{user_id}",
    response_model=UserResponse,
    summary="Update a teacher (admin only)",
    responses={
        403: {"description": "Admin access required"},
        404: {"description": "Teacher not found"},
        409: {"description": "Email or ISIC identifier already in use"},
    },
)
async def update_teacher(
    user_id: int,
    data: UserUpdateRequest,
    _admin: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> UserResponse:
    user = await get_user_by_id(db, user_id)
    if user is None or user.role != UserRole.teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found",
        )
    payload = data.model_dump(exclude_unset=True)
    if "isic_identifier" in payload:
        payload["isic_identifier"] = _require_teacher_isic(
            payload.get("isic_identifier")
        )
    try:
        updated = await update_user(
            db,
            user,
            email=payload.get("email"),
            password=payload.get("password"),
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
            isic_identifier=payload.get("isic_identifier"),
            isic_provided="isic_identifier" in payload,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or ISIC identifier already in use",
        ) from err
    return _user_to_response(updated)


@router.delete(
    "/teachers/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a teacher (admin only)",
    responses={
        403: {"description": "Admin access required"},
        404: {"description": "Teacher not found"},
    },
)
async def delete_teacher(
    user_id: int,
    _admin: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> None:
    user = await get_user_by_id(db, user_id)
    if user is None or user.role != UserRole.teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found",
        )
    await delete_user(db, user)


@router.patch(
    "/me/isic",
    response_model=UserResponse,
    summary="Update current user's ISIC identifier for device pairing",
    responses={409: {"description": "ISIC identifier already used"}},
)
async def update_my_isic(
    data: UserISICUpdateRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> UserResponse:
    try:
        user = await update_user_isic_identifier(
            db, current_user, data.isic_identifier
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ISIC identifier already used",
        ) from err
    return UserResponse(
        id=user.id,
        email=user.email,
        isic_identifier=user.isic_identifier,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role.value,
    )
