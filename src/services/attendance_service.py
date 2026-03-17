from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.attendance import (
    AttendanceRecord,
    AttendanceStatus,
    MarkedBy,
)
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
        scan_timestamp = None
        if record.scan is not None:
            scan_timestamp = record.scan.timestamp
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
