from typing import cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_db
from src.mqtt.client import MQTTClient
from src.models.semester import Semester
from src.models.subject import Subject
from src.models.user import User
from src.services.auth_service import decode_access_token, get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email: str | None = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_user_by_email(db, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(
    user: User = Depends(get_current_user),  # noqa: B008
) -> User:
    if user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def require_teacher_or_admin(user: User) -> None:
    if user.role.value in {"admin", "teacher"}:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Teacher or admin access required",
    )


def ensure_semester_access(user: User, semester: Semester) -> None:
    if user.role.value == "admin":
        return
    if semester.owner_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not your semester",
    )


def ensure_subject_access(user: User, subject: Subject) -> None:
    if user.role.value == "admin":
        return
    if subject.teacher_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not your subject",
    )


def ensure_subject_matches_semester(subject: Subject, semester: Semester) -> None:
    if semester.owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Semester has no owner",
        )
    if subject.teacher_id == semester.owner_id:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Subject does not belong to this semester",
    )


def get_mqtt_client(request: Request) -> MQTTClient:
    mqtt_client = getattr(request.app.state, "mqtt_client", None)
    if mqtt_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MQTT client is not available",
        )
    return cast(MQTTClient, mqtt_client)
