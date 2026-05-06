from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas.enrollment import ImportError_, ImportResult
from src.models.attendance import AttendanceRecord, AttendanceStatus, MarkedBy
from src.models.enrollment import Enrollment
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.subject import Subject
from src.services.scan_service import get_or_create_isic


async def _ensure_subject_exists(session: AsyncSession, subject_id: int) -> None:
    if await session.get(Subject, subject_id) is None:
        raise ValueError("Subject not found")


async def enroll_student(
    session: AsyncSession,
    subject_id: int,
    isic_identifier: str,
    first_name: str,
    last_name: str,
    student_identifier: str | None = None,
    full_name: str | None = None,
    study_identification: str | None = None,
    email_is: str | None = None,
) -> Enrollment:
    await _ensure_subject_exists(session, subject_id)
    isic = await get_or_create_isic(
        session,
        isic_identifier,
        first_name=first_name or None,
        last_name=last_name or None,
        student_identifier=student_identifier,
        full_name=full_name,
        study_identification=study_identification,
        email_is=email_is,
    )

    if isic.first_name is None and first_name:
        isic.first_name = first_name
    if isic.last_name is None and last_name:
        isic.last_name = last_name
    if isic.full_name is None and full_name:
        isic.full_name = full_name
    if isic.student_identifier is None and student_identifier:
        isic.student_identifier = student_identifier
    if isic.study_identification is None and study_identification:
        isic.study_identification = study_identification
    if isic.email_is is None and email_is:
        isic.email_is = email_is

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
    await _ensure_subject_exists(session, subject_id)
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
                student_identifier=row.get("student_identifier"),
                full_name=row.get("full_name"),
                study_identification=row.get("study_identification"),
                email_is=row.get("email_is"),
            )
            imported += 1
        except IntegrityError:
            skipped += 1

    return ImportResult(imported=imported, skipped=skipped, errors=list(errors))
