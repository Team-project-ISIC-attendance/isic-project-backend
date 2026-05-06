import csv
import io

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.attendance import AttendanceRecord
from src.models.enrollment import Enrollment
from src.models.schedule_entry import ScheduleEntry
from src.models.subject import Subject

LESSON_TYPE_LABELS: dict[str, str] = {
    "prednaska": "Prednáška",
    "cvicenie": "Cvičenie",
    "laboratorium": "Laboratórium",
}

ATTENDANCE_STATUS_LABELS: dict[str, str] = {
    "pritomny": "Prítomný",
    "nepritomny": "Neprítomný",
    "nahrada": "Náhrada",
    "ospravedlneny": "Ospravedlnený",
}


async def get_students_data(
    session: AsyncSession, subject_id: int
) -> tuple[
    Subject,
    list[
        tuple[
            str | None,
            str,
            str | None,
            str | None,
            str | None,
            str | None,
        ]
    ],
]:
    """Query enrolled students for a subject.

    Returns student rows sorted by student ID, then name.
    """
    subject_result = await session.execute(
        select(Subject).where(Subject.id == subject_id)
    )
    subject = subject_result.scalar_one()

    result = await session.execute(
        select(Enrollment)
        .where(Enrollment.subject_id == subject_id)
        .options(selectinload(Enrollment.isic))
    )
    enrollments = result.scalars().all()

    students = [
        (
            e.isic.student_identifier,
            e.isic.isic_identifier,
            e.isic.full_name,
            e.isic.first_name,
            e.isic.last_name,
            e.isic.email_is,
        )
        for e in enrollments
    ]
    students.sort(key=lambda s: (s[0] or "", s[4] or "", s[3] or ""))

    return subject, students


async def get_attendance_matrix(
    session: AsyncSession, subject_id: int, semester_id: int
) -> tuple[Subject, list[str], list[list[str]]]:
    """Build attendance matrix for export.

    Returns (subject, column_headers, data_rows) where each data row is
    [student_identifier, isic_identifier, full_name, first_name, last_name, ...].
    """
    subject_result = await session.execute(
        select(Subject).where(Subject.id == subject_id)
    )
    subject = subject_result.scalar_one()

    # Get all schedule entries for this subject in this semester
    entries_result = await session.execute(
        select(ScheduleEntry)
        .where(
            ScheduleEntry.subject_id == subject_id,
            ScheduleEntry.semester_id == semester_id,
        )
        .options(selectinload(ScheduleEntry.lessons))
    )
    entries = entries_result.scalars().all()

    # Collect all lessons sorted by week, day, and start time.
    lesson_info: list[tuple[int, str, str, int, str]] = []
    for entry in entries:
        type_label = LESSON_TYPE_LABELS.get(
            entry.lesson_type.value, entry.lesson_type.value
        )
        time_range = (
            f"{entry.start_time.strftime('%H:%M')}-"
            f"{entry.end_time.strftime('%H:%M')}"
        )
        room = f" {entry.room}" if entry.room else ""
        for lesson in entry.lessons:
            cancelled = " zrušené" if lesson.cancelled else ""
            header = (
                f"Týždeň {lesson.week_number} | {lesson.date.isoformat()} | "
                f"{type_label} | {time_range}{room}{cancelled}"
            )
            sort_key = (
                lesson.week_number,
                lesson.date.isoformat(),
                entry.start_time.strftime("%H:%M"),
            )
            lesson_info.append((*sort_key, lesson.id, header))

    lesson_info.sort(key=lambda x: (x[0], x[1], x[2]))

    column_headers = [header for _, _, _, _, header in lesson_info]
    lesson_ids_ordered = [lesson_id for _, _, _, lesson_id, _ in lesson_info]

    # Get all enrollments with ISIC data
    enroll_result = await session.execute(
        select(Enrollment)
        .where(Enrollment.subject_id == subject_id)
        .options(selectinload(Enrollment.isic))
    )
    enrollments = enroll_result.scalars().all()

    # Build a lookup: (lesson_id, isic_id) -> status
    isic_ids = [e.isic_id for e in enrollments]
    if isic_ids and lesson_ids_ordered:
        att_result = await session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.lesson_id.in_(lesson_ids_ordered),
                AttendanceRecord.isic_id.in_(isic_ids),
            )
        )
        records = att_result.scalars().all()
    else:
        records = []

    status_lookup: dict[tuple[int, int], str] = {
        (r.lesson_id, r.isic_id): r.status.value for r in records
    }

    # Build data rows sorted by last_name
    sorted_enrollments = sorted(
        enrollments,
        key=lambda e: (
            e.isic.student_identifier or "",
            e.isic.last_name or "",
            e.isic.first_name or "",
        ),
    )

    data_rows: list[list[str]] = []
    for enrollment in sorted_enrollments:
        isic = enrollment.isic
        row = [
            isic.student_identifier or "",
            isic.isic_identifier,
            isic.full_name or "",
            isic.first_name or "",
            isic.last_name or "",
        ]
        for lid in lesson_ids_ordered:
            status = status_lookup.get((lid, isic.id), "")
            row.append(ATTENDANCE_STATUS_LABELS.get(status, "Bez záznamu"))
        data_rows.append(row)

    return subject, column_headers, data_rows


def generate_students_csv(
    students_data: list[
        tuple[
            str | None,
            str,
            str | None,
            str | None,
            str | None,
            str | None,
        ]
    ],
) -> str:
    """Generate CSV string for student list with UTF-8 BOM."""
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["ID", "Karta - čip", "Celé meno", "Meno", "Priezvisko", "E-mail IS"])
    for student_id, isic_id, full_name, first_name, last_name, email_is in students_data:
        writer.writerow([
            student_id or "",
            isic_id,
            full_name or "",
            first_name or "",
            last_name or "",
            email_is or "",
        ])
    return output.getvalue()


def generate_students_xlsx(
    students_data: list[
        tuple[
            str | None,
            str,
            str | None,
            str | None,
            str | None,
            str | None,
        ]
    ],
) -> bytes:
    """Generate XLSX bytes for student list."""
    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "Karta - čip", "Celé meno", "Meno", "Priezvisko", "E-mail IS"])
    for student_id, isic_id, full_name, first_name, last_name, email_is in students_data:
        ws.append([
            student_id or "",
            isic_id,
            full_name or "",
            first_name or "",
            last_name or "",
            email_is or "",
        ])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


def generate_attendance_csv(
    column_headers: list[str], data_rows: list[list[str]]
) -> str:
    """Generate CSV string for attendance matrix with UTF-8 BOM."""
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["Študent ID", "Karta - čip", "Celé meno", "Meno", "Priezvisko", *column_headers])
    for row in data_rows:
        writer.writerow(row)
    return output.getvalue()


def generate_attendance_xlsx(
    column_headers: list[str], data_rows: list[list[str]]
) -> bytes:
    """Generate XLSX bytes for attendance matrix."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Študent ID", "Karta - čip", "Celé meno", "Meno", "Priezvisko", *column_headers])
    for row in data_rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
