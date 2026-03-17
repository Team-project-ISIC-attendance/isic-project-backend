from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.lesson import Lesson
from src.models.schedule_entry import LessonType, ScheduleEntry
from src.models.semester import Semester
from src.models.subject import Subject
from src.models.user import User, UserRole


async def create_schedule_entry(
    session: AsyncSession,
    semester_id: int,
    subject_id: int,
    day_of_week: int,
    start_time: str,
    end_time: str,
    room: str | None,
    lesson_type: str,
) -> ScheduleEntry:
    semester = await session.get(Semester, semester_id)
    if semester is None:
        raise ValueError(f"Semester {semester_id} not found")

    parsed_start = datetime.strptime(start_time, "%H:%M").time()
    parsed_end = datetime.strptime(end_time, "%H:%M").time()
    parsed_type = LessonType(lesson_type)

    entry = ScheduleEntry(
        semester_id=semester_id,
        subject_id=subject_id,
        day_of_week=day_of_week,
        start_time=parsed_start,
        end_time=parsed_end,
        room=room,
        lesson_type=parsed_type,
    )
    session.add(entry)
    await session.flush()

    for week in range(1, semester.total_weeks + 1):
        lesson_date = semester.start_date + timedelta(
            days=(week - 1) * 7 + (day_of_week - 1)
        )
        lesson = Lesson(
            schedule_entry_id=entry.id,
            week_number=week,
            date=lesson_date,
            cancelled=False,
        )
        session.add(lesson)

    await session.commit()

    stmt = (
        select(ScheduleEntry)
        .where(ScheduleEntry.id == entry.id)
        .options(selectinload(ScheduleEntry.subject).selectinload(Subject.teacher))
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_schedule_for_semester(
    session: AsyncSession, semester_id: int, user: User
) -> list[ScheduleEntry]:
    stmt = (
        select(ScheduleEntry)
        .where(ScheduleEntry.semester_id == semester_id)
        .options(selectinload(ScheduleEntry.subject))
    )
    if user.role == UserRole.teacher:
        stmt = stmt.join(Subject).where(Subject.teacher_id == user.id)
    result = await session.execute(
        stmt.order_by(ScheduleEntry.day_of_week, ScheduleEntry.start_time)
    )
    return list(result.scalars().all())


async def delete_schedule_entry(
    session: AsyncSession, semester_id: int, entry_id: int
) -> bool:
    stmt = select(ScheduleEntry).where(
        ScheduleEntry.id == entry_id,
        ScheduleEntry.semester_id == semester_id,
    )
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        return False

    await session.execute(
        delete(Lesson).where(Lesson.schedule_entry_id == entry_id)
    )
    await session.delete(entry)
    await session.commit()
    return True


def compute_week_date_range(start_date: date, week_number: int) -> str:
    monday = start_date + timedelta(days=(week_number - 1) * 7)
    friday = monday + timedelta(days=4)
    return f"{monday.day}.{monday.month}. - {friday.day}.{friday.month}."
