from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.enrollment import Enrollment
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.subject import Subject
from src.models.user import User, UserRole


async def create_subject(
    session: AsyncSession,
    name: str,
    code: str,
    color: str,
    teacher_id: int,
) -> Subject:
    subject = Subject(
        name=name,
        code=code,
        color=color,
        teacher_id=teacher_id,
    )
    session.add(subject)
    await session.commit()
    await session.refresh(subject)
    return subject


async def get_subjects_for_user(
    session: AsyncSession, user: User
) -> list[Subject]:
    stmt = select(Subject).options(selectinload(Subject.teacher))
    if user.role == UserRole.teacher:
        stmt = stmt.where(Subject.teacher_id == user.id)
    result = await session.execute(stmt.order_by(Subject.id))
    return list(result.scalars().all())


async def get_subject_by_id(
    session: AsyncSession, subject_id: int
) -> Subject | None:
    stmt = (
        select(Subject)
        .where(Subject.id == subject_id)
        .options(selectinload(Subject.teacher))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_subject(
    session: AsyncSession,
    subject_id: int,
    name: str | None = None,
    code: str | None = None,
    color: str | None = None,
) -> Subject | None:
    subject = await get_subject_by_id(session, subject_id)
    if subject is None:
        return None

    if name is not None:
        subject.name = name
    if code is not None:
        subject.code = code
    if color is not None:
        subject.color = color

    await session.commit()
    await session.refresh(subject)
    return subject


async def delete_subject(
    session: AsyncSession, subject_id: int
) -> bool:
    subject = await get_subject_by_id(session, subject_id)
    if subject is None:
        return False

    await session.execute(
        delete(Lesson).where(
            Lesson.schedule_entry_id.in_(
                select(ScheduleEntry.id).where(
                    ScheduleEntry.subject_id == subject_id
                )
            )
        )
    )
    await session.execute(
        delete(ScheduleEntry).where(ScheduleEntry.subject_id == subject_id)
    )
    await session.execute(
        delete(Enrollment).where(Enrollment.subject_id == subject_id)
    )
    await session.delete(subject)
    await session.commit()
    return True
