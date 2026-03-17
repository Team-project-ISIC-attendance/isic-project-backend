import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from tests.test_auth import create_test_user, get_auth_header


async def _create_subject_with_enrolled_student(
    client: AsyncClient,
    headers: dict[str, str],
    subject_code: str,
    isic_identifier: str = "100000001",
    first_name: str = "Tobias",
    last_name: str = "Banicka",
) -> dict[str, int]:
    """Create semester + subject + schedule entry (13 lessons) + enroll a student.

    Returns dict with semester_id, subject_id, entry_id, enrollment_id, isic_id.
    """
    sem_resp = await client.post(
        "/semesters",
        json={
            "name": "Att Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await client.post(
        "/subjects",
        json={"name": "AttSubj", "code": subject_code, "color": "#4CAF50"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    sched_resp = await client.post(
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
    enroll_body = enroll_resp.json()

    return {
        "semester_id": semester_id,
        "subject_id": subject_id,
        "entry_id": entry_id,
        "enrollment_id": enroll_body["enrollment_id"],
        "isic_id": enroll_body["isic_id"],
    }


@pytest.mark.asyncio
async def test_get_attendance_students(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@att1.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Att1",
    )
    headers = await get_auth_header(test_client, "admin@att1.sk", "pass")
    ids = await _create_subject_with_enrolled_student(
        test_client, headers, "AT01", "100000001", "Tobias", "Banicka"
    )

    # Get lessons list to find a lesson_id
    lessons_resp = await test_client.get(
        f"/semesters/{ids['semester_id']}/schedule/{ids['entry_id']}/lessons",
        headers=headers,
    )
    assert lessons_resp.status_code == 200
    lessons = lessons_resp.json()
    assert len(lessons) == 13
    lesson_id = lessons[0]["id"]

    # Get attendance for the lesson
    att_resp = await test_client.get(
        f"/lessons/{lesson_id}/attendance", headers=headers
    )
    assert att_resp.status_code == 200
    body = att_resp.json()

    # Verify lesson info
    lesson_info = body["lesson"]
    assert lesson_info["id"] == lesson_id
    assert lesson_info["subject_name"] == "AttSubj"
    assert lesson_info["lesson_type"] == "cvicenie"
    assert lesson_info["day_of_week"] == 2
    assert lesson_info["start_time"] == "09:00"
    assert lesson_info["end_time"] == "10:40"
    assert lesson_info["room"] == "B213"
    assert "recurrence" in lesson_info

    # Verify students list
    students = body["students"]
    assert len(students) == 1
    student = students[0]
    assert "attendance_id" in student
    assert student["isic_identifier"] == "100000001"
    assert student["first_name"] == "Tobias"
    assert student["last_name"] == "Banicka"
    assert student["status"] == "nepritomny"
    assert student["marked_by"] == "manual"

    # Verify summary
    summary = body["summary"]
    assert summary["total"] == 1
    assert summary["nepritomny"] == 1
    assert summary["pritomny"] == 0
    assert summary["nahrada"] == 0


@pytest.mark.asyncio
async def test_change_status_pritomny(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@att2.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Att2",
    )
    headers = await get_auth_header(test_client, "admin@att2.sk", "pass")
    ids = await _create_subject_with_enrolled_student(
        test_client, headers, "AT02", "200000001"
    )

    lessons_resp = await test_client.get(
        f"/semesters/{ids['semester_id']}/schedule/{ids['entry_id']}/lessons",
        headers=headers,
    )
    lesson_id = lessons_resp.json()[0]["id"]

    att_resp = await test_client.get(
        f"/lessons/{lesson_id}/attendance", headers=headers
    )
    attendance_id = att_resp.json()["students"][0]["attendance_id"]

    # PATCH to pritomny
    patch_resp = await test_client.patch(
        f"/attendance/{attendance_id}",
        json={"status": "pritomny"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "pritomny"

    # Verify persistence
    att_resp2 = await test_client.get(
        f"/lessons/{lesson_id}/attendance", headers=headers
    )
    assert att_resp2.json()["students"][0]["status"] == "pritomny"


@pytest.mark.asyncio
async def test_change_status_nahrada(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@att3.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Att3",
    )
    headers = await get_auth_header(test_client, "admin@att3.sk", "pass")
    ids = await _create_subject_with_enrolled_student(
        test_client, headers, "AT03", "300000001"
    )

    lessons_resp = await test_client.get(
        f"/semesters/{ids['semester_id']}/schedule/{ids['entry_id']}/lessons",
        headers=headers,
    )
    lesson_id = lessons_resp.json()[0]["id"]

    att_resp = await test_client.get(
        f"/lessons/{lesson_id}/attendance", headers=headers
    )
    attendance_id = att_resp.json()["students"][0]["attendance_id"]

    # PATCH to nahrada
    patch_resp = await test_client.patch(
        f"/attendance/{attendance_id}",
        json={"status": "nahrada"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "nahrada"

    # Verify persistence
    att_resp2 = await test_client.get(
        f"/lessons/{lesson_id}/attendance", headers=headers
    )
    assert att_resp2.json()["students"][0]["status"] == "nahrada"


@pytest.mark.asyncio
async def test_get_week_lessons_summaries(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@att4.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Att4",
    )
    headers = await get_auth_header(test_client, "admin@att4.sk", "pass")
    ids = await _create_subject_with_enrolled_student(
        test_client, headers, "AT04", "400000001"
    )

    week_resp = await test_client.get(
        f"/semesters/{ids['semester_id']}/week/1/lessons",
        headers=headers,
    )
    assert week_resp.status_code == 200
    lessons = week_resp.json()
    assert len(lessons) == 1

    entry = lessons[0]
    assert "lesson_id" in entry
    assert entry["schedule_entry_id"] == ids["entry_id"]
    assert entry["subject_name"] == "AttSubj"
    assert entry["lesson_type"] == "cvicenie"
    assert entry["day_of_week"] == 2
    assert entry["start_time"] == "09:00"
    assert entry["end_time"] == "10:40"
    assert entry["room"] == "B213"

    summary = entry["attendance_summary"]
    assert summary["total"] == 1
    assert summary["nepritomny"] == 1
    assert summary["pritomny"] == 0
    assert summary["nahrada"] == 0


@pytest.mark.asyncio
async def test_cancel_lesson(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@att5.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Att5",
    )
    headers = await get_auth_header(test_client, "admin@att5.sk", "pass")
    ids = await _create_subject_with_enrolled_student(
        test_client, headers, "AT05", "500000001"
    )

    # Get a lesson_id
    lessons_resp = await test_client.get(
        f"/semesters/{ids['semester_id']}/schedule/{ids['entry_id']}/lessons",
        headers=headers,
    )
    lesson_id = lessons_resp.json()[0]["id"]
    assert lessons_resp.json()[0]["cancelled"] is False

    # Cancel the lesson
    patch_resp = await test_client.patch(
        f"/lessons/{lesson_id}",
        json={"cancelled": True},
        headers=headers,
    )
    assert patch_resp.status_code == 200

    # Verify it shows as cancelled
    lessons_resp2 = await test_client.get(
        f"/semesters/{ids['semester_id']}/schedule/{ids['entry_id']}/lessons",
        headers=headers,
    )
    cancelled_lesson = next(
        le for le in lessons_resp2.json() if le["id"] == lesson_id
    )
    assert cancelled_lesson["cancelled"] is True


@pytest.mark.asyncio
async def test_teacher_attendance_isolation(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Admin creates semester (required for semester endpoints)
    await create_test_user(
        db_session, "admin@att6.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Att6",
    )
    admin_headers = await get_auth_header(test_client, "admin@att6.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Iso Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=admin_headers,
    )
    semester_id = sem_resp.json()["id"]

    # Teacher1 creates subject (owns it)
    await create_test_user(
        db_session, "teacher1@att6.sk", "pass", role=UserRole.teacher,
        first_name="Teacher", last_name="One",
    )
    headers1 = await get_auth_header(test_client, "teacher1@att6.sk", "pass")

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "IsoSubj", "code": "AT06", "color": "#4CAF50"},
        headers=headers1,
    )
    subject_id = subj_resp.json()["id"]

    sched_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 2,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B213",
            "lesson_type": "cvicenie",
        },
        headers=headers1,
    )
    entry_id = sched_resp.json()["id"]

    enroll_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "600000001",
            "first_name": "Tobias",
            "last_name": "Banicka",
        },
        headers=headers1,
    )
    assert enroll_resp.status_code == 201

    # Teacher2 does NOT own the subject
    await create_test_user(
        db_session, "teacher2@att6.sk", "pass", role=UserRole.teacher,
        first_name="Teacher", last_name="Two",
    )
    headers2 = await get_auth_header(test_client, "teacher2@att6.sk", "pass")

    # Get a lesson_id via admin (teacher1 can't list semesters)
    lessons_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule/{entry_id}/lessons",
        headers=headers1,
    )
    lesson_id = lessons_resp.json()[0]["id"]

    # Teacher2 tries to access teacher1's lesson attendance -> 403
    att_resp = await test_client.get(
        f"/lessons/{lesson_id}/attendance", headers=headers2
    )
    assert att_resp.status_code == 403


@pytest.mark.asyncio
async def test_attendance_summary_counts(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@att7.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Att7",
    )
    headers = await get_auth_header(test_client, "admin@att7.sk", "pass")

    # Create subject with first student
    ids = await _create_subject_with_enrolled_student(
        test_client, headers, "AT07", "700000001", "Student", "One"
    )

    # Enroll 2 more students
    for i, (fn, ln) in enumerate([("Student", "Two"), ("Student", "Three")], start=2):
        enroll_resp = await test_client.post(
            f"/subjects/{ids['subject_id']}/students",
            json={
                "isic_identifier": f"70000000{i}",
                "first_name": fn,
                "last_name": ln,
            },
            headers=headers,
        )
        assert enroll_resp.status_code == 201

    # Get a lesson
    lessons_resp = await test_client.get(
        f"/semesters/{ids['semester_id']}/schedule/{ids['entry_id']}/lessons",
        headers=headers,
    )
    lesson_id = lessons_resp.json()[0]["id"]

    # Get attendance to find attendance_ids
    att_resp = await test_client.get(
        f"/lessons/{lesson_id}/attendance", headers=headers
    )
    students = att_resp.json()["students"]
    assert len(students) == 3

    # Patch 2 students to pritomny, leave 1 as nepritomny
    for student in students[:2]:
        patch_resp = await test_client.patch(
            f"/attendance/{student['attendance_id']}",
            json={"status": "pritomny"},
            headers=headers,
        )
        assert patch_resp.status_code == 200

    # Verify summary counts
    att_resp2 = await test_client.get(
        f"/lessons/{lesson_id}/attendance", headers=headers
    )
    summary = att_resp2.json()["summary"]
    assert summary["total"] == 3
    assert summary["pritomny"] == 2
    assert summary["nepritomny"] == 1
    assert summary["nahrada"] == 0


@pytest.mark.asyncio
async def test_openapi_schema(test_client: AsyncClient) -> None:
    response = await test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]

    assert "/lessons/{lesson_id}/attendance" in paths
    assert "/attendance/{attendance_id}" in paths
    assert "/semesters/{semester_id}/schedule/{entry_id}/lessons" in paths
    assert "/lessons/{lesson_id}" in paths
    assert "/semesters/{semester_id}/week/{week_number}/lessons" in paths

    all_tags: set[str] = set()
    for path_ops in paths.values():
        for op in path_ops.values():
            if isinstance(op, dict) and "tags" in op:
                all_tags.update(op["tags"])

    assert "attendance" in all_tags
    assert "lessons" in all_tags
