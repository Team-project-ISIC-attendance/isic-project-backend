from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas.enrollment import ImportError_, ImportResult
from src.models.attendance import AttendanceRecord, AttendanceStatus, MarkedBy
from src.models.enrollment import Enrollment
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.services.scan_service import get_or_create_isic


async def enroll_student(
    session: AsyncSession,
    subject_id: int,
    isic_identifier: str,
    first_name: str,
    last_name: str,
) -> Enrollment:
    isic = await get_or_create_isic(session, isic_identifier)

    if isic.first_name is None and first_name:
        isic.first_name = first_name
    if isic.last_name is None and last_name:
        isic.last_name = last_name

    enrollment = Enrollment(
        subject_id=subject_id,
        isic_id=isic.id,
    )
    session.add(enrollment)
    try:
        await session.flush()
    except IntegrityError as err:
        await session.rollback()
        raise err

    lesson_ids_stmt = select(Lesson.id).where(
        Lesson.schedule_entry_id.in_(
            select(ScheduleEntry.id).where(
                ScheduleEntry.subject_id == subject_id
            )
        )
    )
    result = await session.execute(lesson_ids_stmt)
    lesson_ids = result.scalars().all()

    for lesson_id in lesson_ids:
        record = AttendanceRecord(
            lesson_id=lesson_id,
            isic_id=isic.id,
            status=AttendanceStatus.nepritomny,
            marked_by=MarkedBy.manual,
        )
        session.add(record)

    await session.commit()

    reload_stmt = (
        select(Enrollment)
        .where(Enrollment.id == enrollment.id)
        .options(selectinload(Enrollment.isic))
    )
    reload_result = await session.execute(reload_stmt)
    return reload_result.scalar_one()


async def list_enrolled_students(
    session: AsyncSession, subject_id: int
) -> list[Enrollment]:
    stmt = (
        select(Enrollment)
        .where(Enrollment.subject_id == subject_id)
        .options(selectinload(Enrollment.isic))
        .order_by(Enrollment.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_enrollment(
    session: AsyncSession, enrollment_id: int, subject_id: int
) -> bool:
    stmt = select(Enrollment).where(
        Enrollment.id == enrollment_id,
        Enrollment.subject_id == subject_id,
    )
    result = await session.execute(stmt)
    enrollment = result.scalar_one_or_none()
    if enrollment is None:
        return False

    lesson_ids_stmt = select(Lesson.id).where(
        Lesson.schedule_entry_id.in_(
            select(ScheduleEntry.id).where(
                ScheduleEntry.subject_id == subject_id
            )
        )
    )
    await session.execute(
        delete(AttendanceRecord).where(
            AttendanceRecord.isic_id == enrollment.isic_id,
            AttendanceRecord.lesson_id.in_(lesson_ids_stmt),
        )
    )
    await session.delete(enrollment)
    await session.commit()
    return True


async def import_students(
    session: AsyncSession,
    subject_id: int,
    rows: list[dict[str, str]],
    errors: list[ImportError_],
) -> ImportResult:
    imported = 0
    skipped = 0

    for row in rows:
        try:
            await enroll_student(
                session,
                subject_id,
                isic_identifier=row["isic_identifier"],
                first_name=row.get("first_name", ""),
                last_name=row.get("last_name", ""),
            )
            imported += 1
        except IntegrityError:
            skipped += 1

    return ImportResult(imported=imported, skipped=skipped, errors=list(errors))
