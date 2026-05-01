from datetime import date, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.models.attendance import (
    AttendanceRecord,
    AttendanceStatus,
    MarkedBy,
)
from src.models.enrollment import Enrollment
from src.models.isic import ISIC
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.semester import Semester
from src.models.subject import Subject
from src.services.schedule_service import compute_week_date_range

_DAY_NAMES_SK = {
    1: "pondelok",
    2: "utorok",
    3: "streda",
    4: "štvrtok",
    5: "piatok",
}


def _day_name_sk(day: int) -> str:
    return _DAY_NAMES_SK.get(day, str(day))


def _recurrence_label(entry: ScheduleEntry) -> str:
    if entry.is_one_time:
        return "Jednorazovo"
    if entry.recurrence_interval == 1:
        return f"Týždenne v {_day_name_sk(entry.day_of_week)}"
    return (
        f"Každý {entry.recurrence_interval}. týždeň "
        f"v {_day_name_sk(entry.day_of_week)}"
    )


def _same_subject_name(source: Subject, target: Subject) -> bool:
    return source.name.strip().casefold() == target.name.strip().casefold()


def _compute_summary(records: list[AttendanceRecord]) -> dict[str, int]:
    counts = {"total": 0, "pritomny": 0, "nepritomny": 0, "nahrada": 0, "ospravedlneny": 0}
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
    enrollment_result = await session.execute(
        select(Enrollment).where(Enrollment.subject_id == subject.id)
    )
    enrollment_by_isic_id = {
        enrollment.isic_id: enrollment.id
        for enrollment in enrollment_result.scalars().all()
    }

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
        "recurrence": _recurrence_label(entry),
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
            "enrollment_id": enrollment_by_isic_id.get(record.isic_id),
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


async def move_attendance(
    session: AsyncSession,
    attendance_id: int,
    target_lesson_id: int,
) -> AttendanceRecord | str:
    """Move an attendance record to a different lesson.

    Returns the updated record on success, or an error string on failure.
    """
    # Load source attendance with lesson → schedule_entry → subject
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
        return "Attendance record not found"

    source_entry = record.lesson.schedule_entry
    source_subject = source_entry.subject
    source_subject_id = source_subject.id

    # Load target lesson with schedule_entry → subject.
    target_stmt = (
        select(Lesson)
        .where(Lesson.id == target_lesson_id)
        .options(
            selectinload(Lesson.schedule_entry).selectinload(
                ScheduleEntry.subject
            )
        )
    )
    target_result = await session.execute(target_stmt)
    target_lesson = target_result.scalar_one_or_none()
    if target_lesson is None:
        return "Target lesson not found"

    if target_lesson.id == record.lesson_id:
        return "Target lesson is the current lesson"

    target_entry = target_lesson.schedule_entry
    target_subject = target_entry.subject
    target_subject_id = target_subject.id

    if not _same_subject_name(source_subject, target_subject):
        return "Target lesson belongs to a different subject/event"

    target_record_stmt = select(AttendanceRecord).where(
        AttendanceRecord.lesson_id == target_lesson_id,
        AttendanceRecord.isic_id == record.isic_id,
    )
    target_record_result = await session.execute(target_record_stmt)
    target_record = target_record_result.scalar_one_or_none()

    if source_subject_id == target_subject_id:
        record.status = AttendanceStatus.nepritomny
        record.marked_by = MarkedBy.manual
        record.scan_id = None
    else:
        source_enrollment = await session.scalar(
            select(Enrollment).where(
                Enrollment.subject_id == source_subject_id,
                Enrollment.isic_id == record.isic_id,
            )
        )
        if source_enrollment is not None:
            await session.delete(source_enrollment)

        target_enrollment = await session.scalar(
            select(Enrollment).where(
                Enrollment.subject_id == target_subject_id,
                Enrollment.isic_id == record.isic_id,
            )
        )
        if target_enrollment is None:
            session.add(
                Enrollment(
                    subject_id=target_subject_id,
                    isic_id=record.isic_id,
                )
            )

        source_lesson_ids_stmt = select(Lesson.id).where(
            Lesson.schedule_entry_id.in_(
                select(ScheduleEntry.id).where(
                    ScheduleEntry.subject_id == source_subject_id
                )
            )
        )
        await session.execute(
            delete(AttendanceRecord).where(
                AttendanceRecord.isic_id == record.isic_id,
                AttendanceRecord.lesson_id.in_(source_lesson_ids_stmt),
            )
        )

        target_lesson_ids_result = await session.execute(
            select(Lesson.id).where(
                Lesson.schedule_entry_id.in_(
                    select(ScheduleEntry.id).where(
                        ScheduleEntry.subject_id == target_subject_id
                    )
                )
            )
        )
        target_lesson_ids = list(target_lesson_ids_result.scalars().all())
        existing_target_records_result = await session.execute(
            select(AttendanceRecord.lesson_id).where(
                AttendanceRecord.isic_id == record.isic_id,
                AttendanceRecord.lesson_id.in_(target_lesson_ids),
            )
        )
        existing_target_lesson_ids = set(
            existing_target_records_result.scalars().all()
        )
        for lesson_id in target_lesson_ids:
            if lesson_id == target_lesson_id or lesson_id in existing_target_lesson_ids:
                continue
            session.add(
                AttendanceRecord(
                    lesson_id=lesson_id,
                    isic_id=record.isic_id,
                    status=AttendanceStatus.nepritomny,
                    marked_by=MarkedBy.manual,
                )
            )

    if target_record is None:
        target_record = AttendanceRecord(
            lesson_id=target_lesson_id,
            isic_id=record.isic_id,
            status=AttendanceStatus.nahrada,
            marked_by=MarkedBy.manual,
        )
        session.add(target_record)
    else:
        target_record.status = AttendanceStatus.nahrada
        target_record.marked_by = MarkedBy.manual
        target_record.scan_id = None

    await session.commit()
    await session.refresh(target_record)
    return target_record


def _is_current_week(semester_start: date, week_number: int, today: date) -> bool:
    """Check if a week is the current week based on semester start date."""
    monday = semester_start + timedelta(days=(week_number - 1) * 7)
    sunday = monday + timedelta(days=6)
    return monday <= today <= sunday


async def get_schedule_entry_overview(
    session: AsyncSession,
    subject_id: int,
    entry_id: int,
    semester_id: int,
) -> dict[str, object] | None:
    """Get the full attendance overview for a schedule entry across all weeks."""
    # Load entry with subject, lessons (with attendance records + isic)
    stmt = (
        select(ScheduleEntry)
        .where(ScheduleEntry.id == entry_id)
        .options(
            selectinload(ScheduleEntry.subject).selectinload(Subject.teacher),
            selectinload(ScheduleEntry.lessons)
            .selectinload(Lesson.attendance_records)
            .selectinload(AttendanceRecord.isic),
        )
    )
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        return None

    # Validate entry belongs to subject
    if entry.subject_id != subject_id:
        return None

    # Load semester for start_date and total_weeks
    sem_stmt = select(Semester).where(Semester.id == semester_id)
    sem_result = await session.execute(sem_stmt)
    semester = sem_result.scalar_one_or_none()
    if semester is None:
        return None

    subject = entry.subject
    today = date.today()

    # Build lesson lookup: week_number → Lesson
    lesson_map: dict[int, Lesson] = {}
    for lesson in entry.lessons:
        lesson_map[lesson.week_number] = lesson

    # Build weeks list
    weeks: list[dict[str, object]] = []
    for week_num in range(1, semester.total_weeks + 1):
        lesson = lesson_map.get(week_num)
        weeks.append({
            "week_number": week_num,
            "date_range": compute_week_date_range(semester.start_date, week_num),
            "lesson_id": lesson.id if lesson else None,
            "is_current": _is_current_week(semester.start_date, week_num, today),
        })

    # Load enrollments with ISIC data, sorted by (last_name, first_name)
    enroll_stmt = (
        select(Enrollment)
        .where(Enrollment.subject_id == subject_id)
        .options(selectinload(Enrollment.isic))
    )
    enroll_result = await session.execute(enroll_stmt)
    enrollments = list(enroll_result.scalars().all())
    enrollments.sort(
        key=lambda e: (e.isic.last_name or "", e.isic.first_name or "")
    )

    # Build attendance lookup: (lesson_id, isic_id) → AttendanceRecord
    att_lookup: dict[tuple[int, int], AttendanceRecord] = {}
    for lesson in entry.lessons:
        for record in lesson.attendance_records:
            att_lookup[(lesson.id, record.isic_id)] = record

    # Build students list
    students: list[dict[str, object]] = []
    for enrollment in enrollments:
        isic: ISIC = enrollment.isic
        student_weeks: list[dict[str, object]] = []
        for week_num in range(1, semester.total_weeks + 1):
            lesson = lesson_map.get(week_num)
            if lesson is None:
                student_weeks.append({
                    "week_number": week_num,
                    "attendance_id": None,
                    "status": None,
                })
            else:
                record = att_lookup.get((lesson.id, isic.id))
                student_weeks.append({
                    "week_number": week_num,
                    "attendance_id": record.id if record else None,
                    "status": record.status.value if record else None,
                })
        students.append({
            "isic_identifier": isic.isic_identifier,
            "first_name": isic.first_name,
            "last_name": isic.last_name,
            "weeks": student_weeks,
        })

    schedule_entry_info: dict[str, object] = {
        "id": entry.id,
        "subject_name": subject.name,
        "lesson_type": entry.lesson_type.value,
        "start_time": entry.start_time.strftime("%H:%M"),
        "end_time": entry.end_time.strftime("%H:%M"),
        "day_of_week": entry.day_of_week,
        "subject_color": subject.color,
        "recurrence": _recurrence_label(entry),
    }

    return {
        "schedule_entry": schedule_entry_info,
        "weeks": weeks,
        "students": students,
        "teacher_id": subject.teacher_id,
    }


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
