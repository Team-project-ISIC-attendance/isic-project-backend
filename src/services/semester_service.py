from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.semester import Semester
from src.models.week_note import WeekNote


async def create_semester(
    session: AsyncSession,
    name: str,
    start_date: date,
    end_date: date,
    total_weeks: int,
) -> Semester:
    semester = Semester(
        name=name,
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
    await session.delete(semester)
    await session.commit()
    return True
