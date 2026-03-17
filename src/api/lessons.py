from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas.lesson import (
    LessonResponse,
    LessonUpdateRequest,
    WeekLessonResponse,
)
from src.database.connection import get_db
from src.models.user import User, UserRole
from src.services.lesson_service import (
    get_lessons_for_schedule_entry,
    get_week_lessons,
    update_lesson,
)

router = APIRouter(tags=["lessons"])


@router.get(
    "/semesters/{semester_id}/schedule/{entry_id}/lessons",
    response_model=list[LessonResponse],
    summary="Get lessons for a schedule entry",
)
async def list_lessons(
    semester_id: int,
    entry_id: int,
    _user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[LessonResponse]:
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
    lesson = await update_lesson(db, lesson_id, body.cancelled)
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found",
        )
    # Teacher isolation check
    subject = lesson.schedule_entry.subject
    if (
        current_user.role != UserRole.admin
        and subject.teacher_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your subject",
        )
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
    entries = await get_week_lessons(db, semester_id, week_number, current_user)
    return [WeekLessonResponse(**entry) for entry in entries]
