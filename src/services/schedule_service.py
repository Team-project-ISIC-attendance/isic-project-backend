from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.attendance import AttendanceRecord, AttendanceStatus, MarkedBy
from src.models.enrollment import Enrollment
from src.models.lesson import Lesson
from src.models.schedule_entry import LessonType, ScheduleEntry
from src.models.semester import Semester
from src.models.subject import Subject
from src.models.user import User, UserRole


def _parse_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _parse_end_date(value: str | None) -> date | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _iter_lesson_dates(
    semester: Semester,
    day_of_week: int,
    is_one_time: bool,
    recurrence_interval: int,
    end_date: date | None,
) -> dict[int, date]:
    if recurrence_interval < 1:
        raise ValueError("recurrence_interval must be at least 1")

    lesson_dates: dict[int, date] = {}
    for week in range(1, semester.total_weeks + 1):
        if is_one_time and week > 1:
            break
        if recurrence_interval > 1 and (week - 1) % recurrence_interval != 0:
            continue

        lesson_date = semester.start_date + timedelta(
            days=(week - 1) * 7 + (day_of_week - 1)
        )
        if end_date is not None and lesson_date > end_date:
            break
        lesson_dates[week] = lesson_date
    return lesson_dates


async def _add_attendance_records_for_lessons(
    session: AsyncSession,
    subject_id: int,
    lessons: list[Lesson],
) -> None:
    if not lessons:
        return

    result = await session.execute(
        select(Enrollment.isic_id).where(Enrollment.subject_id == subject_id)
    )
    isic_ids = list(result.scalars().all())
    for lesson in lessons:
        for isic_id in isic_ids:
            session.add(
                AttendanceRecord(
                    lesson_id=lesson.id,
                    isic_id=isic_id,
                    status=AttendanceStatus.nepritomny,
                    marked_by=MarkedBy.manual,
                )
            )


async def create_schedule_entry(
    session: AsyncSession,
    semester_id: int,
    subject_id: int,
    day_of_week: int,
    start_time: str,
    end_time: str,
    room: str | None,
    lesson_type: str,
    is_one_time: bool = False,
    recurrence_interval: int = 1,
    end_date: str | None = None,
) -> ScheduleEntry:
    semester = await session.get(Semester, semester_id)
    if semester is None:
        raise ValueError(f"Semester {semester_id} not found")

    parsed_start = _parse_time(start_time)
    parsed_end = _parse_time(end_time)
    parsed_type = LessonType(lesson_type)
    parsed_end_date = _parse_end_date(end_date)

    entry = ScheduleEntry(
        semester_id=semester_id,
        subject_id=subject_id,
        day_of_week=day_of_week,
        start_time=parsed_start,
        end_time=parsed_end,
        room=room,
        lesson_type=parsed_type,
        is_one_time=is_one_time,
        recurrence_interval=recurrence_interval,
        end_date=parsed_end_date,
    )
    session.add(entry)
    await session.flush()

    lesson_dates = _iter_lesson_dates(
        semester,
        day_of_week,
        is_one_time,
        recurrence_interval,
        parsed_end_date,
    )
    created_lessons: list[Lesson] = []
    for week, lesson_date in lesson_dates.items():
        lesson = Lesson(
            schedule_entry_id=entry.id,
            week_number=week,
            date=lesson_date,
            cancelled=False,
        )
        session.add(lesson)
        created_lessons.append(lesson)

    await session.flush()
    await _add_attendance_records_for_lessons(
        session, subject_id, created_lessons
    )

    await session.commit()

    stmt = (
        select(ScheduleEntry)
        .where(ScheduleEntry.id == entry.id)
        .options(selectinload(ScheduleEntry.subject).selectinload(Subject.teacher))
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def update_schedule_entry(
    session: AsyncSession,
    semester_id: int,
    entry_id: int,
    day_of_week: int,
    start_time: str,
    end_time: str,
    room: str | None,
    lesson_type: str,
    is_one_time: bool = False,
    recurrence_interval: int = 1,
    end_date: str | None = None,
    subject_name: str | None = None,
    subject_color: str | None = None,
) -> ScheduleEntry:
    semester = await session.get(Semester, semester_id)
    if semester is None:
        raise ValueError(f"Semester {semester_id} not found")

    stmt = (
        select(ScheduleEntry)
        .where(
            ScheduleEntry.id == entry_id,
            ScheduleEntry.semester_id == semester_id,
        )
        .options(
            selectinload(ScheduleEntry.subject),
            selectinload(ScheduleEntry.lessons).selectinload(
                Lesson.attendance_records
            ),
        )
    )
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        raise ValueError(f"Schedule entry {entry_id} not found")

    parsed_start = _parse_time(start_time)
    parsed_end = _parse_time(end_time)
    parsed_type = LessonType(lesson_type)
    parsed_end_date = _parse_end_date(end_date)

    if subject_name is not None:
        entry.subject.name = subject_name
    if subject_color is not None:
        entry.subject.color = subject_color

    entry.day_of_week = day_of_week
    entry.start_time = parsed_start
    entry.end_time = parsed_end
    entry.room = room
    entry.lesson_type = parsed_type
    entry.is_one_time = is_one_time
    entry.recurrence_interval = recurrence_interval
    entry.end_date = parsed_end_date

    desired_lesson_dates = _iter_lesson_dates(
        semester,
        day_of_week,
        is_one_time,
        recurrence_interval,
        parsed_end_date,
    )
    existing_by_week = {lesson.week_number: lesson for lesson in entry.lessons}

    removed_lessons = [
        lesson
        for week_number, lesson in existing_by_week.items()
        if week_number not in desired_lesson_dates
    ]
    removed_lesson_ids = [lesson.id for lesson in removed_lessons]
    if removed_lesson_ids:
        await session.execute(
            delete(AttendanceRecord).where(
                AttendanceRecord.lesson_id.in_(removed_lesson_ids)
            )
        )
        await session.execute(
            delete(Lesson).where(Lesson.id.in_(removed_lesson_ids))
        )

    created_lessons: list[Lesson] = []
    for week_number, lesson_date in desired_lesson_dates.items():
        lesson = existing_by_week.get(week_number)
        if lesson is None:
            lesson = Lesson(
                schedule_entry_id=entry.id,
                week_number=week_number,
                date=lesson_date,
                cancelled=False,
            )
            session.add(lesson)
            created_lessons.append(lesson)
        else:
            lesson.date = lesson_date

    await session.flush()
    await _add_attendance_records_for_lessons(
        session, entry.subject_id, created_lessons
    )
    await session.commit()

    reload_stmt = (
        select(ScheduleEntry)
        .where(ScheduleEntry.id == entry.id)
        .options(selectinload(ScheduleEntry.subject).selectinload(Subject.teacher))
    )
    reload_result = await session.execute(reload_stmt)
    return reload_result.scalar_one()


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

    lesson_ids_stmt = select(Lesson.id).where(Lesson.schedule_entry_id == entry_id)
    await session.execute(
        delete(AttendanceRecord).where(
            AttendanceRecord.lesson_id.in_(lesson_ids_stmt)
        )
    )
    await session.execute(delete(Lesson).where(Lesson.schedule_entry_id == entry_id))
    await session.delete(entry)
    await session.commit()
    return True


def compute_week_date_range(start_date: date, week_number: int) -> str:
    monday = start_date + timedelta(days=(week_number - 1) * 7)
    friday = monday + timedelta(days=4)
    return f"{monday.day}.{monday.month}. - {friday.day}.{friday.month}."
