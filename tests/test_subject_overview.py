from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from tests.test_auth import create_test_user, get_auth_header


async def _setup_overview(
    client: AsyncClient,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Create semester, subject, 1 schedule entry, enroll 2 students.

    Returns dict with ids for semester, subject, entry, and student identifiers.
    """
    sem_resp = await client.post(
        "/semesters",
        json={
            "name": "Overview Sem",
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
        json={"name": "Overview Subj", "code": "OV001", "color": "#4CAF50"},
        headers=headers,
    )
    assert subj_resp.status_code == 201
    subject_id: int = subj_resp.json()["id"]

    entry_resp = await client.post(
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
    assert entry_resp.status_code == 201
    entry_id: int = entry_resp.json()["id"]

    # Enroll 2 students
    enroll1 = await client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "800000001",
            "first_name": "Alice",
            "last_name": "Novak",
        },
        headers=headers,
    )
    assert enroll1.status_code == 201

    enroll2 = await client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "800000002",
            "first_name": "Bob",
            "last_name": "Kovac",
        },
        headers=headers,
    )
    assert enroll2.status_code == 201

    return {
        "semester_id": semester_id,
        "subject_id": subject_id,
        "entry_id": entry_id,
    }


@pytest.mark.asyncio
async def test_overview_happy_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Happy path: 2 students enrolled, 13 weeks, overview returns full data."""
    await create_test_user(
        db_session, "admin@ov1.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ov1.sk", "pass")
    data = await _setup_overview(test_client, headers)

    resp = await test_client.get(
        f"/subjects/{data['subject_id']}/schedule-entries/{data['entry_id']}/overview",
        params={"semester_id": data["semester_id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    # Check schedule_entry info
    se = body["schedule_entry"]
    assert se["id"] == data["entry_id"]
    assert se["subject_name"] == "Overview Subj"
    assert se["lesson_type"] == "cvicenie"
    assert se["start_time"] == "09:00"
    assert se["end_time"] == "10:40"
    assert se["subject_color"] == "#4CAF50"

    # Check weeks: 13 weeks expected
    weeks = body["weeks"]
    assert len(weeks) == 13
    assert weeks[0]["week_number"] == 1
    assert weeks[12]["week_number"] == 13
    # Each week should have lesson_id (not None for weekly recurrence)
    for w in weeks:
        assert w["lesson_id"] is not None
        assert "date_range" in w
        assert "is_current" in w

    # Check students: 2 enrolled, sorted by last_name
    students = body["students"]
    assert len(students) == 2
    # Kovac before Novak
    assert students[0]["last_name"] == "Kovac"
    assert students[1]["last_name"] == "Novak"
    # Each student has 13 week entries
    for s in students:
        assert len(s["weeks"]) == 13
        for sw in s["weeks"]:
            assert "week_number" in sw
            assert "attendance_id" in sw
            assert "status" in sw


@pytest.mark.asyncio
async def test_overview_current_week_detection(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify is_current is true for at most one week."""
    await create_test_user(
        db_session, "admin@ov2.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ov2.sk", "pass")
    data = await _setup_overview(test_client, headers)

    resp = await test_client.get(
        f"/subjects/{data['subject_id']}/schedule-entries/{data['entry_id']}/overview",
        params={"semester_id": data["semester_id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    weeks = resp.json()["weeks"]

    # At most one week should be current
    current_weeks = [w for w in weeks if w["is_current"]]
    assert len(current_weeks) <= 1


@pytest.mark.asyncio
async def test_overview_empty_enrollment(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Subject with no enrolled students → students array empty, weeks present."""
    await create_test_user(
        db_session, "admin@ov3.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ov3.sk", "pass")

    # Create semester + subject + entry but don't enroll students
    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Empty Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "Empty Subj", "code": "EM001", "color": "#FF0000"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    entry_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 3,
            "start_time": "11:00",
            "end_time": "12:40",
            "room": "A101",
            "lesson_type": "prednaska",
        },
        headers=headers,
    )
    entry_id = entry_resp.json()["id"]

    resp = await test_client.get(
        f"/subjects/{subject_id}/schedule-entries/{entry_id}/overview",
        params={"semester_id": semester_id},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["students"] == []
    assert len(body["weeks"]) == 13


@pytest.mark.asyncio
async def test_overview_teacher_isolation(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Teacher A creates subject → Teacher B cannot access overview → 403."""
    await create_test_user(
        db_session, "teacherA@ov4.sk", "pass", role=UserRole.teacher
    )
    headers_a = await get_auth_header(test_client, "teacherA@ov4.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Isolation Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers_a,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "A Subject", "code": "A001", "color": "#00FF00"},
        headers=headers_a,
    )
    subject_id = subj_resp.json()["id"]

    entry_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "08:00",
            "end_time": "09:40",
            "room": "C301",
            "lesson_type": "cvicenie",
        },
        headers=headers_a,
    )
    entry_id = entry_resp.json()["id"]

    # Teacher B tries to access
    await create_test_user(
        db_session, "teacherB@ov4.sk", "pass", role=UserRole.teacher
    )
    headers_b = await get_auth_header(test_client, "teacherB@ov4.sk", "pass")

    resp = await test_client.get(
        f"/subjects/{subject_id}/schedule-entries/{entry_id}/overview",
        params={"semester_id": semester_id},
        headers=headers_b,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_overview_not_found(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Invalid subject_id or entry_id → 404."""
    await create_test_user(
        db_session, "admin@ov5.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ov5.sk", "pass")

    # Invalid subject
    resp1 = await test_client.get(
        "/subjects/99999/schedule-entries/1/overview",
        params={"semester_id": 1},
        headers=headers,
    )
    assert resp1.status_code == 404

    # Valid subject, invalid entry
    data = await _setup_overview(test_client, headers)
    resp2 = await test_client.get(
        f"/subjects/{data['subject_id']}/schedule-entries/99999/overview",
        params={"semester_id": data["semester_id"]},
        headers=headers,
    )
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_overview_students_sorted(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Enroll 3 students → verify response sorted by last_name, first_name."""
    await create_test_user(
        db_session, "admin@ov6.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@ov6.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Sort Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "Sort Subj", "code": "SO001", "color": "#0000FF"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    entry_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 4,
            "start_time": "14:00",
            "end_time": "15:40",
            "room": "D201",
            "lesson_type": "laboratorium",
        },
        headers=headers,
    )
    entry_id = entry_resp.json()["id"]

    # Enroll 3 students in non-alphabetical order
    for name in [
        ("Charlie", "Zeleny"),
        ("Alice", "Biely"),
        ("Bob", "Biely"),
    ]:
        await test_client.post(
            f"/subjects/{subject_id}/students",
            json={
                "isic_identifier": f"sort{name[0][:3]}",
                "first_name": name[0],
                "last_name": name[1],
            },
            headers=headers,
        )

    resp = await test_client.get(
        f"/subjects/{subject_id}/schedule-entries/{entry_id}/overview",
        params={"semester_id": semester_id},
        headers=headers,
    )
    assert resp.status_code == 200
    students = resp.json()["students"]
    assert len(students) == 3
    # Sorted by last_name, then first_name
    assert students[0]["last_name"] == "Biely"
    assert students[0]["first_name"] == "Alice"
    assert students[1]["last_name"] == "Biely"
    assert students[1]["first_name"] == "Bob"
    assert students[2]["last_name"] == "Zeleny"
