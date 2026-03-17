from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas import SubjectCreate, SubjectResponse, SubjectUpdate
from src.database.connection import get_db
from src.models.user import User, UserRole
from src.services.subject_service import (
    create_subject,
    delete_subject,
    get_subject_by_id,
    get_subjects_for_user,
    update_subject,
)

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _subject_response(subject: "Subject") -> SubjectResponse:  # type: ignore[name-defined]  # noqa: F821
    return SubjectResponse(
        id=subject.id,
        name=subject.name,
        code=subject.code,
        color=subject.color,
        teacher_name=f"{subject.teacher.first_name} {subject.teacher.last_name}",
    )


@router.get(
    "",
    response_model=list[SubjectResponse],
    summary="List subjects",
)
async def list_subjects(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[SubjectResponse]:
    subjects = await get_subjects_for_user(db, current_user)
    return [_subject_response(s) for s in subjects]


@router.post(
    "",
    response_model=SubjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subject",
    responses={409: {"description": "Subject code already exists"}},
)
async def create_subject_endpoint(
    data: SubjectCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> SubjectResponse:
    try:
        subject = await create_subject(
            db,
            name=data.name,
            code=data.code,
            color=data.color,
            teacher_id=current_user.id,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subject code already exists",
        ) from err
    loaded = await get_subject_by_id(db, subject.id)
    assert loaded is not None
    return _subject_response(loaded)


@router.put(
    "/{subject_id}",
    response_model=SubjectResponse,
    summary="Update a subject",
    responses={
        404: {"description": "Subject not found"},
        403: {"description": "Not your subject"},
    },
)
async def update_subject_endpoint(
    subject_id: int,
    data: SubjectUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> SubjectResponse:
    subject = await get_subject_by_id(db, subject_id)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    if current_user.role != UserRole.admin and subject.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your subject",
        )
    updated = await update_subject(
        db, subject_id, name=data.name, code=data.code, color=data.color
    )
    assert updated is not None
    return _subject_response(updated)


@router.delete(
    "/{subject_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a subject",
    responses={
        404: {"description": "Subject not found"},
        403: {"description": "Not your subject"},
    },
)
async def delete_subject_endpoint(
    subject_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    subject = await get_subject_by_id(db, subject_id)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    if current_user.role != UserRole.admin and subject.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your subject",
        )
    await delete_subject(db, subject_id)
    return {"detail": "Subject deleted"}
