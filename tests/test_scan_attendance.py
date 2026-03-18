from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from src.mqtt.client import MQTTClient
from src.services.scan_service import get_scans
from tests.helpers.mqtt_simulator import (
    publish_scan_message,
    wait_for_message_processing,
)
from tests.test_auth import create_test_user, get_auth_header


async def _create_lesson_matching_now(
    client: AsyncClient,
    headers: dict[str, str],
    subject_code: str,
    isic_identifier: str,
    first_name: str = "Test",
    last_name: str = "Student",
) -> dict[str, object]:
    """Create semester + subject + schedule entry + enroll student.

    The lesson is set up so that the current UTC time falls within
    the schedule entry's time window (now - 30min to now + 90min),
    and the semester start_date is Monday of the current week so
    week-1 lesson lands on today.
    """
    now = datetime.now(UTC)
    today = now.date()
    # Monday of the current week
    monday = today - timedelta(days=today.weekday())
    day_of_week = today.isoweekday()

    start_time = (now - timedelta(minutes=30)).strftime("%H:%M")
    end_time = (now + timedelta(minutes=90)).strftime("%H:%M")

    sem_resp = await client.post(
        "/semesters",
        json={
            "name": f"ScanSem-{subject_code}",
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
        json={"name": f"ScanSubj-{subject_code}", "code": subject_code, "color": "#FF5722"},
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
            "room": "A101",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    assert sched_resp.status_code == 201
    entry_id = sched_resp.json()["id"]

    enroll_resp = await client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": isic_identifier,
            "first_name": first_name,
            "last_name": last_name,
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201

    # Find the lesson for today (week 1)
    lessons_resp = await client.get(
        f"/semesters/{semester_id}/schedule/{entry_id}/lessons",
        headers=headers,
    )
    assert lessons_resp.status_code == 200
    lessons = lessons_resp.json()
    today_lesson = next(
        (le for le in lessons if le["date"] == today.isoformat()), None
    )
    assert today_lesson is not None, f"No lesson found for {today.isoformat()}"

    # Get attendance to find the attendance record
    att_resp = await client.get(
        f"/lessons/{today_lesson['id']}/attendance",
        headers=headers,
    )
    assert att_resp.status_code == 200
    students = att_resp.json()["students"]
    attendance_id = students[0]["attendance_id"]

    return {
        "semester_id": semester_id,
        "subject_id": subject_id,
        "entry_id": entry_id,
        "lesson_id": today_lesson["id"],
        "attendance_id": attendance_id,
        "isic_identifier": isic_identifier,
    }


@pytest.mark.asyncio
async def test_scan_during_lesson(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Scan during active lesson -> attendance changes to pritomny."""
    await create_test_user(
        db_session, "admin@scan1.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@scan1.sk", "pass")
    ids = await _create_lesson_matching_now(
        test_client, headers, "SC01", "SCAN_DURING_01",
    )

    await publish_scan_message(mqtt_host, mqtt_port, "SCAN_DURING_01")
    await wait_for_message_processing()

    att_resp = await test_client.get(
        f"/lessons/{ids['lesson_id']}/attendance", headers=headers
    )
    assert att_resp.status_code == 200
    student = att_resp.json()["students"][0]
    assert student["status"] == "pritomny"
    assert student["marked_by"] == "scan"


@pytest.mark.asyncio
async def test_scan_outside_window(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Scan outside lesson time window -> only ISICScan created, no attendance change."""
    await create_test_user(
        db_session, "admin@scan2.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@scan2.sk", "pass")

    now = datetime.now(UTC)
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    day_of_week = today.isoweekday()

    # Lesson at 03:00-03:50 today — well outside current time
    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "ScanSem-SC02",
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
        json={"name": "ScanSubj-SC02", "code": "SC02", "color": "#FF5722"},
        headers=headers,
    )
    assert subj_resp.status_code == 201
    subject_id = subj_resp.json()["id"]

    sched_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": day_of_week,
            "start_time": "03:00",
            "end_time": "03:50",
            "room": "A101",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    assert sched_resp.status_code == 201
    entry_id = sched_resp.json()["id"]

    enroll_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "SCAN_OUTSIDE_01",
            "first_name": "Outside",
            "last_name": "Student",
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201

    # Find today's lesson
    lessons_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{entry_id}/lessons",
        headers=headers,
    )
    today_lesson = next(
        le for le in lessons_resp.json() if le["date"] == today.isoformat()
    )

    await publish_scan_message(mqtt_host, mqtt_port, "SCAN_OUTSIDE_01")
    await wait_for_message_processing()

    # Attendance should remain nepritomny/manual
    att_resp = await test_client.get(
        f"/lessons/{today_lesson['id']}/attendance", headers=headers
    )
    assert att_resp.status_code == 200
    student = att_resp.json()["students"][0]
    assert student["status"] == "nepritomny"
    assert student["marked_by"] == "manual"


@pytest.mark.asyncio
async def test_scan_unenrolled_student(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Scan for an ISIC not enrolled in any subject -> only ISICScan created."""
    await publish_scan_message(mqtt_host, mqtt_port, "SCAN_UNENROLLED_01")
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    found = any(s.isic.isic_identifier == "SCAN_UNENROLLED_01" for s in scans)
    assert found, "ISICScan should be created for unenrolled student"


@pytest.mark.asyncio
async def test_scan_duplicate_idempotent(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Two scans for same ISIC during same lesson -> attendance updated once (first scan_id persists)."""
    await create_test_user(
        db_session, "admin@scan4.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@scan4.sk", "pass")
    ids = await _create_lesson_matching_now(
        test_client, headers, "SC04", "SCAN_DUP_01",
    )

    # First scan
    await publish_scan_message(mqtt_host, mqtt_port, "SCAN_DUP_01")
    await wait_for_message_processing()

    att_resp = await test_client.get(
        f"/lessons/{ids['lesson_id']}/attendance", headers=headers
    )
    student_after_first = att_resp.json()["students"][0]
    assert student_after_first["status"] == "pritomny"
    first_scan_ts = student_after_first["scan_timestamp"]

    # Second scan
    await publish_scan_message(mqtt_host, mqtt_port, "SCAN_DUP_01")
    await wait_for_message_processing()

    att_resp2 = await test_client.get(
        f"/lessons/{ids['lesson_id']}/attendance", headers=headers
    )
    student_after_second = att_resp2.json()["students"][0]
    assert student_after_second["status"] == "pritomny"
    assert student_after_second["scan_timestamp"] == first_scan_ts


@pytest.mark.asyncio
async def test_scan_no_overwrite_manual(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Manual nahrada status not overwritten by scan."""
    await create_test_user(
        db_session, "admin@scan5.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@scan5.sk", "pass")
    ids = await _create_lesson_matching_now(
        test_client, headers, "SC05", "SCAN_MANUAL_01",
    )

    # Manually set to nahrada
    patch_resp = await test_client.patch(
        f"/attendance/{ids['attendance_id']}",
        json={"status": "nahrada"},
        headers=headers,
    )
    assert patch_resp.status_code == 200

    # Scan should NOT overwrite nahrada
    await publish_scan_message(mqtt_host, mqtt_port, "SCAN_MANUAL_01")
    await wait_for_message_processing()

    att_resp = await test_client.get(
        f"/lessons/{ids['lesson_id']}/attendance", headers=headers
    )
    student = att_resp.json()["students"][0]
    assert student["status"] == "nahrada"
    assert student["marked_by"] == "manual"


@pytest.mark.asyncio
async def test_scan_links_attendance(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Scan links to AttendanceRecord via scan_id (scan_timestamp is set)."""
    await create_test_user(
        db_session, "admin@scan6.sk", "pass", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@scan6.sk", "pass")
    ids = await _create_lesson_matching_now(
        test_client, headers, "SC06", "SCAN_LINK_01",
    )

    await publish_scan_message(mqtt_host, mqtt_port, "SCAN_LINK_01")
    await wait_for_message_processing()

    att_resp = await test_client.get(
        f"/lessons/{ids['lesson_id']}/attendance", headers=headers
    )
    student = att_resp.json()["students"][0]
    assert student["scan_timestamp"] is not None
    assert student["status"] == "pritomny"
    assert student["marked_by"] == "scan"


@pytest.mark.asyncio
async def test_existing_mqtt(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Existing behavior: MQTT scan creates ISICScan record even without enrollment."""
    isic_identifier = "EXISTING_MQTT_01"
    await publish_scan_message(mqtt_host, mqtt_port, isic_identifier)
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    found = any(s.isic.isic_identifier == isic_identifier for s in scans)
    assert found, "ISICScan record should be created by existing MQTT handler"
