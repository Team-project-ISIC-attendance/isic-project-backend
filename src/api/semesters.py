from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    ensure_semester_access,
    get_current_user,
    require_teacher_or_admin,
)
from src.api.schemas import SemesterCreate, SemesterResponse
from src.database.connection import get_db
from src.models.user import User
from src.services.semester_service import (
    create_semester,
    delete_semester,
    get_semester_by_id,
    get_semesters_for_user,
)

router = APIRouter(prefix="/semesters", tags=["semesters"])


@router.get(
    "",
    response_model=list[SemesterResponse],
    summary="List all semesters",
)
async def list_semesters(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[SemesterResponse]:
    semesters = await get_semesters_for_user(db, current_user)
    return [
        SemesterResponse(
            id=s.id,
            name=s.name,
            start_date=s.start_date,
            end_date=s.end_date,
            total_weeks=s.total_weeks,
        )
        for s in semesters
    ]


@router.post(
    "",
    response_model=SemesterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a semester",
    responses={409: {"description": "Semester name already exists"}},
)
async def create_semester_endpoint(
    data: SemesterCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> SemesterResponse:
    require_teacher_or_admin(current_user)
    try:
        semester = await create_semester(
            db,
            name=data.name,
            start_date=data.start_date,
            end_date=data.end_date,
            total_weeks=data.total_weeks,
            owner_id=current_user.id,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Semester name already exists",
        ) from err
    return SemesterResponse(
        id=semester.id,
        name=semester.name,
        start_date=semester.start_date,
        end_date=semester.end_date,
        total_weeks=semester.total_weeks,
    )


@router.delete(
    "/{semester_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a semester",
    responses={404: {"description": "Semester not found"}},
)
async def delete_semester_endpoint(
    semester_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    require_teacher_or_admin(current_user)
    semester = await get_semester_by_id(db, semester_id)
    if semester is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Semester not found",
        )
    ensure_semester_access(current_user, semester)
    deleted = await delete_semester(db, semester_id)
    assert deleted
    return {"detail": "Semester deleted"}
