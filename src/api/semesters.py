from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import require_admin
from src.api.schemas import SemesterCreate, SemesterResponse
from src.database.connection import get_db
from src.models.user import User
from src.services.semester_service import (
    create_semester,
    delete_semester,
    get_all_semesters,
)

router = APIRouter(prefix="/semesters", tags=["semesters"])


@router.get(
    "",
    response_model=list[SemesterResponse],
    summary="List all semesters",
)
async def list_semesters(
    _user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[SemesterResponse]:
    semesters = await get_all_semesters(db)
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
    _admin: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> SemesterResponse:
    try:
        semester = await create_semester(
            db,
            name=data.name,
            start_date=data.start_date,
            end_date=data.end_date,
            total_weeks=data.total_weeks,
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
    _admin: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    deleted = await delete_semester(db, semester_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Semester not found",
        )
    return {"detail": "Semester deleted"}
