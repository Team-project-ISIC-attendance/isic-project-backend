from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.user import User, UserRole
from src.services.scan_service import normalize_isic_identifier

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def verify_password(plain: str, hashed: str) -> bool:
    result: bool = pwd_context.verify(plain, hashed)
    return result


def hash_password(password: str) -> str:
    result: str = pwd_context.hash(password)
    return result


def create_access_token(
    data: dict[str, str | datetime],
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(hours=settings.jwt_expiry_hours)
    )
    to_encode["exp"] = expire
    encoded_jwt: str = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, str] | None:
    try:
        payload: dict[str, str] = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[ALGORITHM]
        )
        return payload
    except JWTError:
        return None


async def get_user_by_email(
    session: AsyncSession, email: str
) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> User | None:
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def create_user(
    session: AsyncSession,
    email: str,
    hashed_password: str,
    isic_identifier: str | None,
    first_name: str,
    last_name: str,
    role: UserRole,
) -> User:
    user = User(
        email=email,
        hashed_password=hashed_password,
        isic_identifier=(
            normalize_isic_identifier(isic_identifier)
            if isic_identifier
            else None
        ),
        first_name=first_name,
        last_name=last_name,
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def ensure_admin_exists(session: AsyncSession) -> None:
    result = await session.execute(select(User).limit(1))
    if result.scalar_one_or_none() is not None:
        return
    await create_user(
        session=session,
        email=settings.admin_email,
        hashed_password=hash_password(settings.admin_password),
        isic_identifier=None,
        first_name="Admin",
        last_name="User",
        role=UserRole.admin,
    )


async def update_user_isic_identifier(
    session: AsyncSession,
    user: User,
    isic_identifier: str | None,
) -> User:
    user.isic_identifier = (
        normalize_isic_identifier(isic_identifier)
        if isic_identifier
        else None
    )
    await session.commit()
    await session.refresh(user)
    return user


async def list_users_by_role(
    session: AsyncSession, role: UserRole
) -> list[User]:
    result = await session.execute(
        select(User).where(User.role == role).order_by(User.last_name, User.first_name)
    )
    return list(result.scalars().all())


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_user(
    session: AsyncSession,
    user: User,
    *,
    email: str | None = None,
    password: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    isic_identifier: str | None = None,
    isic_provided: bool = False,
) -> User:
    if email is not None:
        user.email = email
    if password is not None and password != "":
        user.hashed_password = hash_password(password)
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    if isic_provided:
        user.isic_identifier = (
            normalize_isic_identifier(isic_identifier)
            if isic_identifier
            else None
        )
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user: User) -> None:
    await session.delete(user)
    await session.commit()
