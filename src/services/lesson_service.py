from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.attendance import AttendanceRecord
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.subject import Subject
from src.models.user import User, UserRole


async def get_lessons_for_schedule_entry(
    session: AsyncSession, entry_id: int
) -> list[Lesson]:
    stmt = (
        select(Lesson)
        .where(Lesson.schedule_entry_id == entry_id)
        .order_by(Lesson.week_number)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_lesson(
    session: AsyncSession, lesson_id: int, cancelled: bool | None
) -> Lesson | None:
    stmt = (
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(
            selectinload(Lesson.schedule_entry).selectinload(
                ScheduleEntry.subject
            ),
        )
    )
    result = await session.execute(stmt)
    lesson = result.scalar_one_or_none()
    if lesson is None:
        return None

    if cancelled is not None:
        lesson.cancelled = cancelled
    await session.commit()

    reload_stmt = (
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(
            selectinload(Lesson.schedule_entry).selectinload(
                ScheduleEntry.subject
            ),
        )
    )
    reload_result = await session.execute(reload_stmt)
    return reload_result.scalar_one()


async def get_week_lessons(
    session: AsyncSession, semester_id: int, week_number: int, user: User
) -> list[dict[str, object]]:
    stmt = (
        select(Lesson)
        .join(Lesson.schedule_entry)
        .join(ScheduleEntry.subject)
        .where(
            ScheduleEntry.semester_id == semester_id,
            Lesson.week_number == week_number,
        )
        .options(
            selectinload(Lesson.schedule_entry).selectinload(
                ScheduleEntry.subject
            ),
        )
    )

    if user.role == UserRole.teacher:
        stmt = stmt.where(Subject.teacher_id == user.id)

    result = await session.execute(stmt)
    lessons = list(result.scalars().all())

    if not lessons:
        return []

    # Fetch attendance counts in a single query to avoid N+1
    lesson_ids = [lesson.id for lesson in lessons]
    counts_stmt = (
        select(
            AttendanceRecord.lesson_id,
            AttendanceRecord.status,
            func.count().label("cnt"),
        )
        .where(AttendanceRecord.lesson_id.in_(lesson_ids))
        .group_by(AttendanceRecord.lesson_id, AttendanceRecord.status)
    )
    counts_result = await session.execute(counts_stmt)

    # Build summary dict: lesson_id -> {status -> count}
    summary_map: dict[int, dict[str, int]] = {}
    for row in counts_result:
        lid = row.lesson_id
        if lid not in summary_map:
            summary_map[lid] = {
                "total": 0,
                "pritomny": 0,
                "nepritomny": 0,
                "nahrada": 0,
            }
        status_val = row.status if isinstance(row.status, str) else row.status.value
        summary_map[lid][status_val] += row.cnt
        summary_map[lid]["total"] += row.cnt

    entries = []
    for lesson in lessons:
        entry = lesson.schedule_entry
        subject = entry.subject
        summary = summary_map.get(lesson.id, {
            "total": 0,
            "pritomny": 0,
            "nepritomny": 0,
            "nahrada": 0,
        })
        entries.append({
            "lesson_id": lesson.id,
            "schedule_entry_id": entry.id,
            "subject_name": subject.name,
            "lesson_type": entry.lesson_type.value,
            "day_of_week": entry.day_of_week,
            "start_time": entry.start_time.strftime("%H:%M"),
            "end_time": entry.end_time.strftime("%H:%M"),
            "room": entry.room,
            "attendance_summary": summary,
        })

    return entries
