from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.dependencies import (
    ensure_semester_access,
    ensure_subject_access,
    get_current_user,
    require_teacher_or_admin,
)
from src.api.schemas.lesson import (
    LessonResponse,
    LessonUpdateRequest,
    WeekLessonResponse,
)
from src.database.connection import get_db
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.user import User
from src.services.lesson_service import (
    get_lessons_for_schedule_entry,
    get_week_lessons,
    update_lesson,
)
from src.services.semester_service import get_semester_by_id

router = APIRouter(tags=["lessons"])


async def _get_lesson_or_404(db: AsyncSession, lesson_id: int) -> Lesson:
    stmt = (
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(
            selectinload(Lesson.schedule_entry).selectinload(
                ScheduleEntry.subject
            ),
        )
    )
    result = await db.execute(stmt)
    lesson = result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found",
        )
    return lesson


async def _get_schedule_entry_or_404(
    db: AsyncSession,
    semester_id: int,
    entry_id: int,
) -> ScheduleEntry:
    stmt = (
        select(ScheduleEntry)
        .where(
            ScheduleEntry.id == entry_id,
            ScheduleEntry.semester_id == semester_id,
        )
        .options(selectinload(ScheduleEntry.subject))
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule entry not found",
        )
    return entry


@router.get(
    "/semesters/{semester_id}/schedule/{entry_id}/lessons",
    response_model=list[LessonResponse],
    summary="Get lessons for a schedule entry",
)
async def list_lessons(
    semester_id: int,
    entry_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[LessonResponse]:
    semester = await get_semester_by_id(db, semester_id)
    if semester is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Semester not found",
        )
    ensure_semester_access(current_user, semester)
    entry = await _get_schedule_entry_or_404(db, semester_id, entry_id)
    ensure_subject_access(current_user, entry.subject)
    lessons = await get_lessons_for_schedule_entry(db, entry_id)
    return [
        LessonResponse(
            id=lesson.id,
            week_number=lesson.week_number,
            date=lesson.date.isoformat(),
            cancelled=lesson.cancelled,
        )
        for lesson in lessons
    ]


@router.patch(
    "/lessons/{lesson_id}",
    response_model=LessonResponse,
    summary="Update a lesson",
    responses={
        404: {"description": "Lesson not found"},
        403: {"description": "Not your subject"},
    },
)
async def patch_lesson(
    lesson_id: int,
    body: LessonUpdateRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> LessonResponse:
    require_teacher_or_admin(current_user)
    existing = await _get_lesson_or_404(db, lesson_id)
    ensure_subject_access(current_user, existing.schedule_entry.subject)
    lesson = await update_lesson(db, lesson_id, body.cancelled)
    assert lesson is not None
    return LessonResponse(
        id=lesson.id,
        week_number=lesson.week_number,
        date=lesson.date.isoformat(),
        cancelled=lesson.cancelled,
    )


@router.get(
    "/semesters/{semester_id}/week/{week_number}/lessons",
    response_model=list[WeekLessonResponse],
    summary="Get all lessons for a week with attendance summaries",
)
async def get_week(
    semester_id: int,
    week_number: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[WeekLessonResponse]:
    semester = await get_semester_by_id(db, semester_id)
    if semester is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Semester not found",
        )
    ensure_semester_access(current_user, semester)
    entries = await get_week_lessons(db, semester_id, week_number, current_user)
    return [WeekLessonResponse(**entry) for entry in entries]
