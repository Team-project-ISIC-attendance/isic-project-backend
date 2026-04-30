from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from tests.test_auth import create_test_user, get_auth_header


async def _setup_two_entries(
    client: AsyncClient,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Create semester, subject, 2 schedule entries, enroll student.

    Returns dict with ids for semester, subject, entries, enrollment, isic,
    and the first lesson ids for each entry.
    """
    sem_resp = await client.post(
        "/semesters",
        json={
            "name": "Event Panel Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    assert sem_resp.status_code == 201
    semester_id: int = sem_resp.json()["id"]

    subj_resp = await client.post(
        "/subjects",
        json={"name": "EP Subj", "code": "EP001", "color": "#4CAF50"},
        headers=headers,
    )
    assert subj_resp.status_code == 201
    subject_id: int = subj_resp.json()["id"]

    # Entry 1: Tuesday
    entry1_resp = await client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 2,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B213",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    assert entry1_resp.status_code == 201
    entry1_id: int = entry1_resp.json()["id"]

    # Entry 2: Thursday (same subject)
    entry2_resp = await client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 4,
            "start_time": "13:00",
            "end_time": "14:40",
            "room": "B214",
            "lesson_type": "prednaska",
        },
        headers=headers,
    )
    assert entry2_resp.status_code == 201
    entry2_id: int = entry2_resp.json()["id"]

    # Enroll student
    enroll_resp = await client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "900000001",
            "first_name": "Peter",
            "last_name": "Novak",
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201
    enroll_body = enroll_resp.json()

    # Get lesson ids for entry 1 and entry 2
    lessons1_resp = await client.get(
        f"/semesters/{semester_id}/schedule/{entry1_id}/lessons",
        headers=headers,
    )
    assert lessons1_resp.status_code == 200
    entry1_lessons: list[dict[str, object]] = lessons1_resp.json()

    lessons2_resp = await client.get(
        f"/semesters/{semester_id}/schedule/{entry2_id}/lessons",
        headers=headers,
    )
    assert lessons2_resp.status_code == 200
    entry2_lessons: list[dict[str, object]] = lessons2_resp.json()

    return {
        "semester_id": semester_id,
        "subject_id": subject_id,
        "entry1_id": entry1_id,
        "entry2_id": entry2_id,
        "enrollment_id": enroll_body["enrollment_id"],
        "isic_id": enroll_body["isic_id"],
        "entry1_lesson_ids": [lesson["id"] for lesson in entry1_lessons],
        "entry2_lesson_ids": [lesson["id"] for lesson in entry2_lessons],
    }


@pytest.mark.asyncio
async def test_update_attendance_ospravedlneny(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test: Update attendance to ospravedlneny status via PATCH."""
    await create_test_user(
        db_session, "admin@ep1.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ep1.sk", "pass")
    data = await _setup_two_entries(test_client, headers)

    entry1_lesson_ids = data["entry1_lesson_ids"]
    assert len(entry1_lesson_ids) > 0
    first_lesson_id = entry1_lesson_ids[0]

    # Get attendance for first lesson
    att_resp = await test_client.get(
        f"/lessons/{first_lesson_id}/attendance",
        headers=headers,
    )
    assert att_resp.status_code == 200
    students = att_resp.json()["students"]
    assert len(students) == 1
    attendance_id = students[0]["attendance_id"]

    # Update to ospravedlneny
    patch_resp = await test_client.patch(
        f"/attendance/{attendance_id}",
        json={"status": "ospravedlneny"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "ospravedlneny"
    assert patch_resp.json()["marked_by"] == "manual"


@pytest.mark.asyncio
async def test_attendance_summary_includes_ospravedlneny(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test: GET attendance summary includes ospravedlneny count."""
    await create_test_user(
        db_session, "admin@ep2.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ep2.sk", "pass")
    data = await _setup_two_entries(test_client, headers)

    entry1_lesson_ids = data["entry1_lesson_ids"]
    first_lesson_id = entry1_lesson_ids[0]

    # Get attendance and set status to ospravedlneny
    att_resp = await test_client.get(
        f"/lessons/{first_lesson_id}/attendance",
        headers=headers,
    )
    attendance_id = att_resp.json()["students"][0]["attendance_id"]

    await test_client.patch(
        f"/attendance/{attendance_id}",
        json={"status": "ospravedlneny"},
        headers=headers,
    )

    # Re-fetch and check summary
    att_resp2 = await test_client.get(
        f"/lessons/{first_lesson_id}/attendance",
        headers=headers,
    )
    assert att_resp2.status_code == 200
    summary = att_resp2.json()["summary"]
    assert summary["ospravedlneny"] == 1
    assert summary["nepritomny"] == 0


@pytest.mark.asyncio
async def test_move_attendance_success(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test: POST move attendance marks the target lesson as a replacement."""
    await create_test_user(
        db_session, "admin@ep3.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ep3.sk", "pass")
    data = await _setup_two_entries(test_client, headers)

    entry1_lesson_ids = data["entry1_lesson_ids"]
    entry2_lesson_ids = data["entry2_lesson_ids"]
    first_lesson_id = entry1_lesson_ids[0]
    target_lesson_id = entry2_lesson_ids[0]

    # Get attendance for first lesson
    att_resp = await test_client.get(
        f"/lessons/{first_lesson_id}/attendance",
        headers=headers,
    )
    attendance_id = att_resp.json()["students"][0]["attendance_id"]

    # Move to target lesson
    move_resp = await test_client.post(
        f"/attendance/{attendance_id}/move",
        json={"target_lesson_id": target_lesson_id},
        headers=headers,
    )
    assert move_resp.status_code == 200
    assert move_resp.json()["lesson_id"] == target_lesson_id
    assert move_resp.json()["attendance_id"] != attendance_id
    assert move_resp.json()["status"] == "nahrada"

    source_resp = await test_client.get(
        f"/lessons/{first_lesson_id}/attendance",
        headers=headers,
    )
    target_resp = await test_client.get(
        f"/lessons/{target_lesson_id}/attendance",
        headers=headers,
    )
    assert source_resp.status_code == 200
    assert target_resp.status_code == 200
    assert source_resp.json()["students"][0]["status"] == "nepritomny"
    assert target_resp.json()["students"][0]["status"] == "nahrada"


@pytest.mark.asyncio
async def test_move_attendance_different_subject_fails(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test: POST move to lesson in different subject returns 400."""
    await create_test_user(
        db_session, "admin@ep4.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ep4.sk", "pass")
    data = await _setup_two_entries(test_client, headers)

    entry1_lesson_ids = data["entry1_lesson_ids"]
    first_lesson_id = entry1_lesson_ids[0]
    semester_id = data["semester_id"]

    # Create a different subject + entry
    subj2_resp = await test_client.post(
        "/subjects",
        json={"name": "Other Subj", "code": "OTH001", "color": "#FF0000"},
        headers=headers,
    )
    assert subj2_resp.status_code == 201
    other_subject_id = subj2_resp.json()["id"]

    entry3_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": other_subject_id,
            "day_of_week": 3,
            "start_time": "11:00",
            "end_time": "12:40",
            "room": "C101",
            "lesson_type": "prednaska",
        },
        headers=headers,
    )
    assert entry3_resp.status_code == 201
    entry3_id = entry3_resp.json()["id"]

    lessons3_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{entry3_id}/lessons",
        headers=headers,
    )
    other_lesson_id = lessons3_resp.json()[0]["id"]

    # Get attendance
    att_resp = await test_client.get(
        f"/lessons/{first_lesson_id}/attendance",
        headers=headers,
    )
    attendance_id = att_resp.json()["students"][0]["attendance_id"]

    # Try to move to different subject's lesson
    move_resp = await test_client.post(
        f"/attendance/{attendance_id}/move",
        json={"target_lesson_id": other_lesson_id},
        headers=headers,
    )
    assert move_resp.status_code == 400
    assert "different subject" in move_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_move_attendance_existing_target_record_succeeds(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test: POST move updates the pre-created target attendance record."""
    await create_test_user(
        db_session, "admin@ep5.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ep5.sk", "pass")
    data = await _setup_two_entries(test_client, headers)

    entry1_lesson_ids = data["entry1_lesson_ids"]
    first_lesson_id = entry1_lesson_ids[0]
    entry2_lesson_ids = data["entry2_lesson_ids"]
    target_lesson_id = entry2_lesson_ids[0]

    # Get attendance
    att_resp = await test_client.get(
        f"/lessons/{first_lesson_id}/attendance",
        headers=headers,
    )
    attendance_id = att_resp.json()["students"][0]["attendance_id"]

    move_resp = await test_client.post(
        f"/attendance/{attendance_id}/move",
        json={"target_lesson_id": target_lesson_id},
        headers=headers,
    )
    assert move_resp.status_code == 200
    assert move_resp.json()["lesson_id"] == target_lesson_id
    assert move_resp.json()["status"] == "nahrada"


@pytest.mark.asyncio
async def test_move_attendance_same_lesson_fails(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test: POST move to the current lesson returns 400."""
    await create_test_user(
        db_session, "admin@ep7.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ep7.sk", "pass")
    data = await _setup_two_entries(test_client, headers)

    first_lesson_id = data["entry1_lesson_ids"][0]

    att_resp = await test_client.get(
        f"/lessons/{first_lesson_id}/attendance",
        headers=headers,
    )
    attendance_id = att_resp.json()["students"][0]["attendance_id"]

    move_resp = await test_client.post(
        f"/attendance/{attendance_id}/move",
        json={"target_lesson_id": first_lesson_id},
        headers=headers,
    )
    assert move_resp.status_code == 400
    assert "current lesson" in move_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_move_attendance_not_found(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test: POST move non-existent attendance returns 404."""
    await create_test_user(
        db_session, "admin@ep6.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ep6.sk", "pass")

    move_resp = await test_client.post(
        "/attendance/99999/move",
        json={"target_lesson_id": 1},
        headers=headers,
    )
    assert move_resp.status_code == 404
