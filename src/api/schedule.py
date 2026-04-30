from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas import (
    ScheduleEntryCreate,
    ScheduleEntryResponse,
    ScheduleEntryUpdate,
)
from src.database.connection import get_db
from src.models.user import User
from src.services.schedule_service import (
    create_schedule_entry,
    delete_schedule_entry,
    get_schedule_for_semester,
    update_schedule_entry,
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
        is_one_time=entry.is_one_time,
        recurrence_interval=entry.recurrence_interval,
        end_date=entry.end_date.isoformat() if entry.end_date else None,
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
            is_one_time=data.is_one_time,
            recurrence_interval=data.recurrence_interval,
            end_date=data.end_date,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    return _entry_response(entry)


@router.put(
    "/{entry_id}",
    response_model=ScheduleEntryResponse,
    summary="Update a schedule entry",
    responses={
        400: {"description": "Invalid schedule data"},
        404: {"description": "Semester or schedule entry not found"},
        409: {"description": "Subject update conflict"},
    },
)
async def update_schedule(
    semester_id: int,
    entry_id: int,
    data: ScheduleEntryUpdate,
    _user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ScheduleEntryResponse:
    try:
        entry = await update_schedule_entry(
            db,
            semester_id=semester_id,
            entry_id=entry_id,
            day_of_week=data.day_of_week,
            start_time=data.start_time,
            end_time=data.end_time,
            room=data.room,
            lesson_type=data.lesson_type,
            is_one_time=data.is_one_time,
            recurrence_interval=data.recurrence_interval,
            end_date=data.end_date,
            subject_name=data.subject_name,
            subject_color=data.subject_color,
        )
    except IntegrityError as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Schedule entry conflict: one schedule entry can only have "
                "one lesson in the same semester week"
            ),
        ) from err
    except ValueError as err:
        detail = str(err)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=detail) from err
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
