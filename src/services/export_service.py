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


async def get_students_data(
    session: AsyncSession, subject_id: int
) -> tuple[Subject, list[tuple[str, str | None, str | None]]]:
    """Query enrolled students for a subject.

    Returns (subject, list of (isic_identifier, first_name, last_name)) sorted
    by last_name.
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

    students: list[tuple[str, str | None, str | None]] = [
        (e.isic.isic_identifier, e.isic.first_name, e.isic.last_name)
        for e in enrollments
    ]
    students.sort(key=lambda s: (s[2] or "", s[1] or ""))

    return subject, students


async def get_attendance_matrix(
    session: AsyncSession, subject_id: int, semester_id: int
) -> tuple[Subject, list[str], list[list[str]]]:
    """Build attendance matrix for export.

    Returns (subject, column_headers, data_rows) where each data row is
    [isic_identifier, first_name, last_name, status1, status2, ...].
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

    # Collect all lessons sorted by (week_number, lesson_type)
    lesson_info: list[tuple[int, int, str]] = []  # (week_number, lesson_id, type_label)
    for entry in entries:
        type_label = entry.lesson_type.value.capitalize()
        for lesson in entry.lessons:
            lesson_info.append((lesson.week_number, lesson.id, type_label))

    lesson_info.sort(key=lambda x: (x[0], x[2]))

    column_headers = [f"T{week} {label}" for week, _, label in lesson_info]
    lesson_ids_ordered = [lid for _, lid, _ in lesson_info]

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
        key=lambda e: (e.isic.last_name or "", e.isic.first_name or ""),
    )

    data_rows: list[list[str]] = []
    for enrollment in sorted_enrollments:
        isic = enrollment.isic
        row = [isic.isic_identifier, isic.first_name or "", isic.last_name or ""]
        for lid in lesson_ids_ordered:
            status = status_lookup.get((lid, isic.id), "")
            row.append(status)
        data_rows.append(row)

    return subject, column_headers, data_rows


def generate_students_csv(
    students_data: list[tuple[str, str | None, str | None]],
) -> str:
    """Generate CSV string for student list with UTF-8 BOM."""
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["ISIC", "Meno", "Priezvisko"])
    for isic_id, first_name, last_name in students_data:
        writer.writerow([isic_id, first_name or "", last_name or ""])
    return output.getvalue()


def generate_students_xlsx(
    students_data: list[tuple[str, str | None, str | None]],
) -> bytes:
    """Generate XLSX bytes for student list."""
    wb = Workbook()
    ws = wb.active
    ws.append(["ISIC", "Meno", "Priezvisko"])
    for isic_id, first_name, last_name in students_data:
        ws.append([isic_id, first_name or "", last_name or ""])
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
    writer.writerow(["ISIC", "Meno", "Priezvisko", *column_headers])
    for row in data_rows:
        writer.writerow(row)
    return output.getvalue()


def generate_attendance_xlsx(
    column_headers: list[str], data_rows: list[list[str]]
) -> bytes:
    """Generate XLSX bytes for attendance matrix."""
    wb = Workbook()
    ws = wb.active
    ws.append(["ISIC", "Meno", "Priezvisko", *column_headers])
    for row in data_rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
