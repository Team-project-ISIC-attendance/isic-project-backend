from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas import ScheduleEntryCreate, ScheduleEntryResponse
from src.database.connection import get_db
from src.models.user import User
from src.services.schedule_service import (
    create_schedule_entry,
    delete_schedule_entry,
    get_schedule_for_semester,
)
from src.services.semester_service import get_semester_by_id

router = APIRouter(
    prefix="/semesters/{semester_id}/schedule", tags=["schedule"]
)


def _entry_response(entry: "ScheduleEntry") -> ScheduleEntryResponse:  # type: ignore[name-defined]  # noqa: F821
    return ScheduleEntryResponse(
        id=entry.id,
        subject_id=entry.subject_id,
        subject_name=entry.subject.name,
        subject_code=entry.subject.code,
        subject_color=entry.subject.color,
        day_of_week=entry.day_of_week,
        start_time=entry.start_time.strftime("%H:%M"),
        end_time=entry.end_time.strftime("%H:%M"),
        room=entry.room,
        lesson_type=entry.lesson_type.value,
    )


@router.get(
    "",
    response_model=list[ScheduleEntryResponse],
    summary="Get schedule for a semester",
    responses={404: {"description": "Semester not found"}},
)
async def get_schedule(
    semester_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[ScheduleEntryResponse]:
    semester = await get_semester_by_id(db, semester_id)
    if semester is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Semester not found",
        )
    entries = await get_schedule_for_semester(db, semester_id, current_user)
    return [_entry_response(e) for e in entries]


@router.post(
    "",
    response_model=ScheduleEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a schedule entry",
    responses={404: {"description": "Semester or subject not found"}},
)
async def create_schedule(
    semester_id: int,
    data: ScheduleEntryCreate,
    _user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ScheduleEntryResponse:
    try:
        entry = await create_schedule_entry(
            db,
            semester_id=semester_id,
            subject_id=data.subject_id,
            day_of_week=data.day_of_week,
            start_time=data.start_time,
            end_time=data.end_time,
            room=data.room,
            lesson_type=data.lesson_type,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    return _entry_response(entry)


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a schedule entry",
    responses={404: {"description": "Schedule entry not found"}},
)
async def delete_schedule(
    semester_id: int,
    entry_id: int,
    _user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    deleted = await delete_schedule_entry(db, semester_id, entry_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule entry not found",
        )
    return {"detail": "Schedule entry deleted"}
