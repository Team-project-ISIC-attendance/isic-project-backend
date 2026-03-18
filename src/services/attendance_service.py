from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.models.attendance import (
    AttendanceRecord,
    AttendanceStatus,
    MarkedBy,
)
from src.models.enrollment import Enrollment
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.subject import Subject

_DAY_NAMES_SK = {
    1: "pondelok",
    2: "utorok",
    3: "streda",
    4: "štvrtok",
    5: "piatok",
}


def _day_name_sk(day: int) -> str:
    return _DAY_NAMES_SK.get(day, str(day))


def _compute_summary(records: list[AttendanceRecord]) -> dict[str, int]:
    counts = {"total": 0, "pritomny": 0, "nepritomny": 0, "nahrada": 0}
    for record in records:
        counts["total"] += 1
        counts[record.status.value] += 1
    return counts


async def get_lesson_attendance(
    session: AsyncSession, lesson_id: int
) -> dict[str, object] | None:
    stmt = (
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(
            selectinload(Lesson.schedule_entry).selectinload(
                ScheduleEntry.subject
            ).selectinload(Subject.teacher),
            selectinload(Lesson.attendance_records).selectinload(
                AttendanceRecord.isic
            ),
            selectinload(Lesson.attendance_records).selectinload(
                AttendanceRecord.scan
            ),
        )
    )
    result = await session.execute(stmt)
    lesson = result.scalar_one_or_none()
    if lesson is None:
        return None

    entry = lesson.schedule_entry
    subject = entry.subject

    lesson_info = {
        "id": lesson.id,
        "subject_name": subject.name,
        "subject_color": subject.color,
        "lesson_type": entry.lesson_type.value,
        "week_number": lesson.week_number,
        "date": lesson.date.isoformat(),
        "start_time": entry.start_time.strftime("%H:%M"),
        "end_time": entry.end_time.strftime("%H:%M"),
        "room": entry.room,
        "day_of_week": entry.day_of_week,
        "recurrence": f"Tyzdenne v {_day_name_sk(entry.day_of_week)}",
    }

    sorted_records = sorted(
        lesson.attendance_records,
        key=lambda r: (r.isic.last_name or "", r.isic.first_name or ""),
    )

    students = []
    for record in sorted_records:
        scan_timestamp: str | None = None
        if record.scan is not None:
            scan_timestamp = record.scan.timestamp.isoformat()
        students.append({
            "attendance_id": record.id,
            "isic_identifier": record.isic.isic_identifier,
            "first_name": record.isic.first_name,
            "last_name": record.isic.last_name,
            "status": record.status.value,
            "marked_by": record.marked_by.value,
            "scan_timestamp": scan_timestamp,
        })

    summary = _compute_summary(list(lesson.attendance_records))

    return {
        "lesson": lesson_info,
        "students": students,
        "summary": summary,
        "teacher_id": subject.teacher_id,
    }


async def update_attendance_status(
    session: AsyncSession, attendance_id: int, status_str: str
) -> AttendanceRecord | None:
    stmt = (
        select(AttendanceRecord)
        .where(AttendanceRecord.id == attendance_id)
        .options(
            selectinload(AttendanceRecord.lesson)
            .selectinload(Lesson.schedule_entry)
            .selectinload(ScheduleEntry.subject),
        )
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        return None

    record.status = AttendanceStatus(status_str)
    record.marked_by = MarkedBy.manual
    await session.commit()
    await session.refresh(record)
    return record


async def try_auto_record(
    session: AsyncSession,
    isic_id: int,
    scan_id: int,
    scan_timestamp: datetime,
) -> list[AttendanceRecord]:
    """Try to auto-record attendance for an ISIC scan.

    Finds active lessons within the scan time window and updates
    attendance records from nepritomny/manual to pritomny/scan.
    """
    scan_date = scan_timestamp.date()
    scan_naive = scan_timestamp.replace(tzinfo=None)

    # Find all subjects this ISIC is enrolled in
    enroll_stmt = select(Enrollment.subject_id).where(
        Enrollment.isic_id == isic_id
    )
    enroll_result = await session.execute(enroll_stmt)
    subject_ids = list(enroll_result.scalars().all())

    if not subject_ids:
        logger.debug("No enrollments found for isic_id={}", isic_id)
        return []

    # Find lessons on scan_date for enrolled subjects (not cancelled)
    lesson_stmt = (
        select(Lesson)
        .join(ScheduleEntry, Lesson.schedule_entry_id == ScheduleEntry.id)
        .where(
            Lesson.date == scan_date,
            Lesson.cancelled == False,  # noqa: E712
            ScheduleEntry.subject_id.in_(subject_ids),
        )
        .options(selectinload(Lesson.schedule_entry))
    )
    lesson_result = await session.execute(lesson_stmt)
    lessons = list(lesson_result.scalars().all())

    if not lessons:
        logger.debug("No lessons found on {} for enrolled subjects", scan_date)
        return []

    updated: list[AttendanceRecord] = []

    for lesson in lessons:
        entry = lesson.schedule_entry
        window_start = datetime.combine(
            scan_date, entry.start_time
        ) - timedelta(minutes=settings.scan_window_before_minutes)
        window_end = datetime.combine(
            scan_date, entry.end_time
        ) + timedelta(minutes=settings.scan_window_after_minutes)

        if not (window_start <= scan_naive <= window_end):
            continue

        # Find the attendance record for this lesson + ISIC
        att_stmt = select(AttendanceRecord).where(
            AttendanceRecord.lesson_id == lesson.id,
            AttendanceRecord.isic_id == isic_id,
        )
        att_result = await session.execute(att_stmt)
        record = att_result.scalar_one_or_none()

        if record is None:
            continue

        # Idempotent: already scanned
        if record.scan_id is not None:
            continue

        # Preserve manual overrides (status != nepritomny set by teacher)
        if (
            record.marked_by == MarkedBy.manual
            and record.status != AttendanceStatus.nepritomny
        ):
            continue

        record.status = AttendanceStatus.pritomny
        record.marked_by = MarkedBy.scan
        record.scan_id = scan_id
        updated.append(record)

    if updated:
        await session.commit()

    return updated
