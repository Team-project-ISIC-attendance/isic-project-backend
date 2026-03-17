from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas import WeekNoteUpdate, WeekResponse
from src.database.connection import get_db
from src.models.user import User
from src.models.week_note import WeekNote
from src.services.schedule_service import compute_week_date_range
from src.services.semester_service import get_semester_by_id

router = APIRouter(
    prefix="/semesters/{semester_id}/weeks", tags=["weeks"]
)


@router.get(
    "",
    response_model=list[WeekResponse],
    summary="Get weeks with notes for a semester",
    responses={404: {"description": "Semester not found"}},
)
async def get_weeks(
    semester_id: int,
    _user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[WeekResponse]:
    semester = await get_semester_by_id(db, semester_id)
    if semester is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Semester not found",
        )
    result = await db.execute(
        select(WeekNote)
        .where(WeekNote.semester_id == semester_id)
        .order_by(WeekNote.week_number)
    )
    week_notes = result.scalars().all()
    return [
        WeekResponse(
            week_number=wn.week_number,
            note=wn.note,
            date_range=compute_week_date_range(
                semester.start_date, wn.week_number
            ),
        )
        for wn in week_notes
    ]


@router.patch(
    "/{week_number}",
    response_model=WeekResponse,
    summary="Update a week note",
    responses={404: {"description": "Week not found"}},
)
async def update_week_note(
    semester_id: int,
    week_number: int,
    data: WeekNoteUpdate,
    _user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> WeekResponse:
    result = await db.execute(
        select(WeekNote).where(
            WeekNote.semester_id == semester_id,
            WeekNote.week_number == week_number,
        )
    )
    week_note = result.scalar_one_or_none()
    if week_note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Week not found",
        )
    week_note.note = data.note
    await db.commit()
    await db.refresh(week_note)

    semester = await get_semester_by_id(db, semester_id)
    assert semester is not None
    return WeekResponse(
        week_number=week_note.week_number,
        note=week_note.note,
        date_range=compute_week_date_range(
            semester.start_date, week_note.week_number
        ),
    )
