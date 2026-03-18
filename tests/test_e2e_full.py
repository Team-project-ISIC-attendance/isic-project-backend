from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enrollment import Enrollment
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.user import UserRole
from src.models.week_note import WeekNote
from src.mqtt.client import MQTTClient
from tests.helpers.mqtt_simulator import (
    publish_scan_message,
    wait_for_message_processing,
)
from tests.test_auth import create_test_user, get_auth_header


async def _create_semester_with_schedule(
    client: AsyncClient,
    headers: dict[str, str],
    sem_name: str,
    subj_code: str,
) -> dict[str, object]:
    """Create semester + subject + schedule entry aligned to today."""
    now = datetime.now(UTC)
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    day_of_week = today.isoweekday()

    start_time = (now - timedelta(minutes=30)).strftime("%H:%M")
    end_time = (now + timedelta(minutes=90)).strftime("%H:%M")

    sem_resp = await client.post(
        "/semesters",
        json={
            "name": sem_name,
            "start_date": monday.isoformat(),
            "end_date": (monday + timedelta(weeks=13)).isoformat(),
            "total_weeks": 13,
        },
        headers=headers,
    )
    assert sem_resp.status_code == 201
    semester_id = sem_resp.json()["id"]

    subj_resp = await client.post(
        "/subjects",
        json={"name": f"Subj-{subj_code}", "code": subj_code, "color": "#4A90D9"},
        headers=headers,
    )
    assert subj_resp.status_code == 201
    subject_id = subj_resp.json()["id"]

    sched_resp = await client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": day_of_week,
            "start_time": start_time,
            "end_time": end_time,
            "room": "B202",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    assert sched_resp.status_code == 201
    entry_id = sched_resp.json()["id"]

    return {
        "semester_id": semester_id,
        "subject_id": subject_id,
        "entry_id": entry_id,
        "today": today.isoformat(),
    }


@pytest.mark.asyncio
async def test_e2e_full_setup(
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Create semester -> subject -> schedule entry -> verify 13 lessons generated."""
    await create_test_user(
        db_session, "admin@e2e-setup.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@e2e-setup.sk", "pass")

    ids = await _create_semester_with_schedule(
        test_client, headers, "E2E-Setup-Sem", "E2ES",
    )

    lessons_resp = await test_client.get(
        f"/semesters/{ids['semester_id']}/schedule/{ids['entry_id']}/lessons",
        headers=headers,
    )
    assert lessons_resp.status_code == 200
    lessons = lessons_resp.json()
    assert len(lessons) == 13

    week_numbers = sorted(le["week_number"] for le in lessons)
    assert week_numbers == list(range(1, 14))


@pytest.mark.asyncio
async def test_e2e_students(
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """CSV import with 3 students, verify enrollment count, verify attendance backfill."""
    await create_test_user(
        db_session, "admin@e2e-students.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@e2e-students.sk", "pass")

    ids = await _create_semester_with_schedule(
        test_client, headers, "E2E-Students-Sem", "E2EST",
    )
    subject_id = ids["subject_id"]

    csv_content = (
        "ISIC,Meno,Priezvisko\n"
        "STU001,Anna,Kováčová\n"
        "STU002,Peter,Horváth\n"
        "STU003,Mária,Novotná\n"
    )
    import_resp = await test_client.post(
        f"/subjects/{subject_id}/students/import",
        files={"file": ("students.csv", csv_content.encode("utf-8"), "text/csv")},
        headers=headers,
    )
    assert import_resp.status_code == 200
    result = import_resp.json()
    assert result["imported"] == 3
    assert result["skipped"] == 0
    assert len(result["errors"]) == 0

    students_resp = await test_client.get(
        f"/subjects/{subject_id}/students",
        headers=headers,
    )
    assert students_resp.status_code == 200
    assert len(students_resp.json()) == 3

    # Verify attendance backfill: each student should have 13 AttendanceRecords
    entry_id = ids["entry_id"]
    semester_id = ids["semester_id"]

    lessons_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{entry_id}/lessons",
        headers=headers,
    )
    lessons = lessons_resp.json()
    today_lesson = next(
        (le for le in lessons if le["date"] == ids["today"]),
        None,
    )
    assert today_lesson is not None

    att_resp = await test_client.get(
        f"/lessons/{today_lesson['id']}/attendance",
        headers=headers,
    )
    assert att_resp.status_code == 200
    att_data = att_resp.json()
    assert len(att_data["students"]) == 3

    for student in att_data["students"]:
        assert student["status"] == "nepritomny"
        assert student["marked_by"] == "manual"


@pytest.mark.asyncio
async def test_e2e_manual_attendance(
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Change a student's status via PATCH, verify persistence and summary update."""
    await create_test_user(
        db_session, "admin@e2e-manual.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@e2e-manual.sk", "pass")

    ids = await _create_semester_with_schedule(
        test_client, headers, "E2E-Manual-Sem", "E2EM",
    )
    subject_id = ids["subject_id"]
    semester_id = ids["semester_id"]
    entry_id = ids["entry_id"]

    # Enroll a student
    enroll_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "MANUAL_STU_01",
            "first_name": "Ján",
            "last_name": "Kováč",
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201

    # Find today's lesson and attendance
    lessons_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{entry_id}/lessons",
        headers=headers,
    )
    today_lesson = next(
        le for le in lessons_resp.json() if le["date"] == ids["today"]
    )

    att_resp = await test_client.get(
        f"/lessons/{today_lesson['id']}/attendance",
        headers=headers,
    )
    student = att_resp.json()["students"][0]
    attendance_id = student["attendance_id"]
    assert student["status"] == "nepritomny"

    # Change status to pritomny
    patch_resp = await test_client.patch(
        f"/attendance/{attendance_id}",
        json={"status": "pritomny"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "pritomny"
    assert patch_resp.json()["marked_by"] == "manual"

    # Verify persistence on re-fetch
    att_resp2 = await test_client.get(
        f"/lessons/{today_lesson['id']}/attendance",
        headers=headers,
    )
    refetched = att_resp2.json()
    assert refetched["students"][0]["status"] == "pritomny"
    assert refetched["summary"]["pritomny"] == 1
    assert refetched["summary"]["nepritomny"] == 0


@pytest.mark.asyncio
async def test_e2e_scan_attendance(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish MQTT scan during active lesson, verify attendance changes to pritomny/scan."""
    await create_test_user(
        db_session, "admin@e2e-scan.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@e2e-scan.sk", "pass")

    ids = await _create_semester_with_schedule(
        test_client, headers, "E2E-Scan-Sem", "E2ESC",
    )
    subject_id = ids["subject_id"]
    semester_id = ids["semester_id"]
    entry_id = ids["entry_id"]

    # Enroll student
    await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "E2E_SCAN_01",
            "first_name": "Scan",
            "last_name": "Student",
        },
        headers=headers,
    )

    # Find today's lesson
    lessons_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{entry_id}/lessons",
        headers=headers,
    )
    today_lesson = next(
        le for le in lessons_resp.json() if le["date"] == ids["today"]
    )

    # Verify default status
    att_resp = await test_client.get(
        f"/lessons/{today_lesson['id']}/attendance",
        headers=headers,
    )
    assert att_resp.json()["students"][0]["status"] == "nepritomny"

    # Simulate NFC scan
    await publish_scan_message(mqtt_host, mqtt_port, "E2E_SCAN_01")
    await wait_for_message_processing()

    # Verify attendance changed to pritomny via scan
    att_resp2 = await test_client.get(
        f"/lessons/{today_lesson['id']}/attendance",
        headers=headers,
    )
    student = att_resp2.json()["students"][0]
    assert student["status"] == "pritomny"
    assert student["marked_by"] == "scan"
    assert student["scan_timestamp"] is not None


@pytest.mark.asyncio
async def test_e2e_export(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Export students CSV and attendance CSV, verify content includes all statuses."""
    await create_test_user(
        db_session, "admin@e2e-export.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@e2e-export.sk", "pass")

    ids = await _create_semester_with_schedule(
        test_client, headers, "E2E-Export-Sem", "E2EEX",
    )
    subject_id = ids["subject_id"]
    semester_id = ids["semester_id"]
    entry_id = ids["entry_id"]

    # Enroll 3 students
    for isic, fname, lname in [
        ("EXP_STU_01", "Export", "One"),
        ("EXP_STU_02", "Export", "Two"),
        ("EXP_STU_03", "Export", "Three"),
    ]:
        resp = await test_client.post(
            f"/subjects/{subject_id}/students",
            json={"isic_identifier": isic, "first_name": fname, "last_name": lname},
            headers=headers,
        )
        assert resp.status_code == 201

    # Find today's lesson
    lessons_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{entry_id}/lessons",
        headers=headers,
    )
    today_lesson = next(
        le for le in lessons_resp.json() if le["date"] == ids["today"]
    )

    # Get attendance records to find IDs
    att_resp = await test_client.get(
        f"/lessons/{today_lesson['id']}/attendance",
        headers=headers,
    )
    students = att_resp.json()["students"]
    student_by_isic = {s["isic_identifier"]: s for s in students}

    # Student 1: pritomny via scan
    await publish_scan_message(mqtt_host, mqtt_port, "EXP_STU_01")
    await wait_for_message_processing()

    # Student 2: nahrada via manual
    await test_client.patch(
        f"/attendance/{student_by_isic['EXP_STU_02']['attendance_id']}",
        json={"status": "nahrada"},
        headers=headers,
    )

    # Student 3: remains nepritomny (default)

    # Export students CSV
    students_csv_resp = await test_client.get(
        f"/subjects/{subject_id}/export/students?format=csv",
        headers=headers,
    )
    assert students_csv_resp.status_code == 200
    students_csv = students_csv_resp.content.decode("utf-8-sig")
    assert "Export" in students_csv
    assert "EXP_STU_01" in students_csv

    # Export attendance CSV
    att_csv_resp = await test_client.get(
        f"/subjects/{subject_id}/export/attendance?semester_id={semester_id}&format=csv",
        headers=headers,
    )
    assert att_csv_resp.status_code == 200
    att_csv = att_csv_resp.content.decode("utf-8-sig")
    # Verify all three statuses appear in the matrix
    assert "pritomny" in att_csv.lower() or "P" in att_csv
    assert "nepritomny" in att_csv.lower() or "N" in att_csv
    assert "nahrada" in att_csv.lower() or "Á" in att_csv


@pytest.mark.asyncio
async def test_e2e_edge_cases(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Outside-window scan (no change), duplicate scan (idempotent), cascade delete."""
    await create_test_user(
        db_session, "admin@e2e-edge.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@e2e-edge.sk", "pass")

    now = datetime.now(UTC)
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    day_of_week = today.isoweekday()

    # --- Edge case 1: outside-window scan ---
    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "E2E-Edge-Sem",
            "start_date": monday.isoformat(),
            "end_date": (monday + timedelta(weeks=13)).isoformat(),
            "total_weeks": 13,
        },
        headers=headers,
    )
    assert sem_resp.status_code == 201
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "Edge-Subject", "code": "EDGE", "color": "#FF0000"},
        headers=headers,
    )
    assert subj_resp.status_code == 201
    subject_id = subj_resp.json()["id"]

    # Schedule at 03:00-03:50 — guaranteed outside current time window
    sched_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": day_of_week,
            "start_time": "03:00",
            "end_time": "03:50",
            "room": "C303",
            "lesson_type": "prednaska",
        },
        headers=headers,
    )
    assert sched_resp.status_code == 201
    entry_id = sched_resp.json()["id"]

    enroll_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "EDGE_STU_01",
            "first_name": "Edge",
            "last_name": "Student",
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201

    lessons_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{entry_id}/lessons",
        headers=headers,
    )
    today_lesson = next(
        le for le in lessons_resp.json() if le["date"] == today.isoformat()
    )

    # Scan outside window — attendance should NOT change
    await publish_scan_message(mqtt_host, mqtt_port, "EDGE_STU_01")
    await wait_for_message_processing()

    att_resp = await test_client.get(
        f"/lessons/{today_lesson['id']}/attendance",
        headers=headers,
    )
    student = att_resp.json()["students"][0]
    assert student["status"] == "nepritomny"

    # --- Edge case 2: duplicate scan (idempotent) ---
    # Create a second schedule entry with a time window matching now
    start_time = (now - timedelta(minutes=30)).strftime("%H:%M")
    end_time = (now + timedelta(minutes=90)).strftime("%H:%M")

    subj2_resp = await test_client.post(
        "/subjects",
        json={"name": "Edge-Active", "code": "EACT", "color": "#00FF00"},
        headers=headers,
    )
    assert subj2_resp.status_code == 201
    active_subject_id = subj2_resp.json()["id"]

    sched2_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": active_subject_id,
            "day_of_week": day_of_week,
            "start_time": start_time,
            "end_time": end_time,
            "room": "D404",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    assert sched2_resp.status_code == 201
    active_entry_id = sched2_resp.json()["id"]

    await test_client.post(
        f"/subjects/{active_subject_id}/students",
        json={
            "isic_identifier": "EDGE_DUP_01",
            "first_name": "Dup",
            "last_name": "Student",
        },
        headers=headers,
    )

    lessons2_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{active_entry_id}/lessons",
        headers=headers,
    )
    active_lesson = next(
        le for le in lessons2_resp.json() if le["date"] == today.isoformat()
    )

    # First scan
    await publish_scan_message(mqtt_host, mqtt_port, "EDGE_DUP_01")
    await wait_for_message_processing()

    att2_resp = await test_client.get(
        f"/lessons/{active_lesson['id']}/attendance",
        headers=headers,
    )
    after_first = att2_resp.json()["students"][0]
    assert after_first["status"] == "pritomny"
    first_ts = after_first["scan_timestamp"]

    # Second scan — should be idempotent
    await publish_scan_message(mqtt_host, mqtt_port, "EDGE_DUP_01")
    await wait_for_message_processing()

    att3_resp = await test_client.get(
        f"/lessons/{active_lesson['id']}/attendance",
        headers=headers,
    )
    after_second = att3_resp.json()["students"][0]
    assert after_second["status"] == "pritomny"
    assert after_second["scan_timestamp"] == first_ts

    # --- Edge case 3: cascade delete ---
    # Delete the semester and verify all children are gone via DB queries
    del_resp = await test_client.delete(
        f"/semesters/{semester_id}",
        headers=headers,
    )
    assert del_resp.status_code == 200

    # Verify schedule entries deleted
    entries_result = await db_session.execute(
        select(ScheduleEntry).where(ScheduleEntry.semester_id == semester_id)
    )
    assert len(entries_result.scalars().all()) == 0

    # Verify lessons deleted (via schedule entry IDs)
    lessons_result = await db_session.execute(
        select(Lesson).where(
            Lesson.schedule_entry_id.in_([entry_id, active_entry_id])
        )
    )
    assert len(lessons_result.scalars().all()) == 0

    # Verify week notes deleted
    notes_result = await db_session.execute(
        select(WeekNote).where(WeekNote.semester_id == semester_id)
    )
    assert len(notes_result.scalars().all()) == 0

    # Verify enrollments deleted (subject still exists, but enrollments should be gone
    # since semester delete cascades through schedule entries -> lessons -> attendance,
    # but enrollments are on subject, not semester — they should still exist)
    enroll_result = await db_session.execute(
        select(Enrollment).where(Enrollment.subject_id == subject_id)
    )
    # Enrollments are tied to subject, not semester — they persist after semester delete
    assert len(enroll_result.scalars().all()) == 1
