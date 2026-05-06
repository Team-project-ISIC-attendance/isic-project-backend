from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.attendance import AttendanceRecord
from src.models.enrollment import Enrollment
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.semester import Semester
from src.models.subject import Subject
from src.models.week_note import WeekNote
from src.models.user import User, UserRole


async def create_semester(
    session: AsyncSession,
    name: str,
    start_date: date,
    end_date: date,
    total_weeks: int,
    owner_id: int | None,
) -> Semester:
    semester = Semester(
        name=name,
        owner_id=owner_id,
        start_date=start_date,
        end_date=end_date,
        total_weeks=total_weeks,
    )
    session.add(semester)
    await session.flush()

    for week_number in range(1, total_weeks + 1):
        week_note = WeekNote(
            semester_id=semester.id,
            week_number=week_number,
            note="",
        )
        session.add(week_note)

    await session.commit()
    await session.refresh(semester)
    return semester


async def get_all_semesters(session: AsyncSession) -> list[Semester]:
    result = await session.execute(
        select(Semester).order_by(Semester.id)
    )
    return list(result.scalars().all())


async def get_semesters_for_user(
    session: AsyncSession, user: User
) -> list[Semester]:
    stmt = select(Semester)
    if user.role == UserRole.teacher:
        stmt = stmt.where(Semester.owner_id == user.id)
    result = await session.execute(stmt.order_by(Semester.id))
    return list(result.scalars().all())


async def get_semester_by_id(
    session: AsyncSession, semester_id: int
) -> Semester | None:
    return await session.get(Semester, semester_id)


async def delete_semester(
    session: AsyncSession, semester_id: int
) -> bool:
    semester = await session.get(Semester, semester_id)
    if semester is None:
        return False

    subject_ids_result = await session.execute(
        select(ScheduleEntry.subject_id)
        .where(ScheduleEntry.semester_id == semester_id)
        .distinct()
    )
    subject_ids = list(subject_ids_result.scalars().all())
    reusable_subject_ids_result = await session.execute(
        select(ScheduleEntry.subject_id)
        .where(
            ScheduleEntry.subject_id.in_(subject_ids),
            ScheduleEntry.semester_id != semester_id,
        )
        .distinct()
    )
    reusable_subject_ids = set(reusable_subject_ids_result.scalars().all())
    delete_subject_ids = [
        subject_id
        for subject_id in subject_ids
        if subject_id not in reusable_subject_ids
    ]

    lesson_ids_stmt = select(Lesson.id).where(
        Lesson.schedule_entry_id.in_(
            select(ScheduleEntry.id).where(
                ScheduleEntry.semester_id == semester_id
            )
        )
    )
    await session.execute(
        delete(AttendanceRecord).where(
            AttendanceRecord.lesson_id.in_(lesson_ids_stmt)
        )
    )
    await session.execute(
        delete(Lesson).where(
            Lesson.schedule_entry_id.in_(
                select(ScheduleEntry.id).where(
                    ScheduleEntry.semester_id == semester_id
                )
            )
        )
    )
    await session.execute(
        delete(ScheduleEntry).where(ScheduleEntry.semester_id == semester_id)
    )
    await session.execute(
        delete(WeekNote).where(WeekNote.semester_id == semester_id)
    )
    if delete_subject_ids:
        await session.execute(
            delete(Enrollment).where(
                Enrollment.subject_id.in_(delete_subject_ids)
            )
        )
        await session.execute(
            delete(Subject).where(Subject.id.in_(delete_subject_ids))
        )
    await session.delete(semester)
    await session.commit()
    return True
