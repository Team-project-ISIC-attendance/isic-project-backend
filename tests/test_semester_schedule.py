import io
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.attendance import AttendanceRecord
from src.models.enrollment import Enrollment
from src.models.lesson import Lesson
from src.models.subject import Subject
from src.models.user import UserRole
from tests.test_auth import create_test_user, get_auth_header


@pytest.mark.asyncio
async def test_create_semester_weeks_auto(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@sem.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="User",
    )
    headers = await get_auth_header(test_client, "admin@sem.sk", "pass")

    response = await test_client.post(
        "/semesters",
        json={
            "name": "25/26 LS",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["name"] == "25/26 LS"
    assert body["start_date"] == "2026-02-16"
    assert body["end_date"] == "2026-05-16"
    assert body["total_weeks"] == 13

    semester_id = body["id"]
    weeks_resp = await test_client.get(
        f"/semesters/{semester_id}/weeks", headers=headers
    )
    assert weeks_resp.status_code == 200
    weeks = weeks_resp.json()
    assert len(weeks) == 13
    for week in weeks:
        assert "week_number" in week
        assert "note" in week
        assert "date_range" in week


@pytest.mark.asyncio
async def test_create_subject_visible(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "teacher@subj.sk", "pass",
        first_name="Jan", last_name="Novak",
    )
    headers = await get_auth_header(test_client, "teacher@subj.sk", "pass")

    response = await test_client.post(
        "/subjects",
        json={"name": "Algoritmy", "code": "ADS", "color": "#4CAF50"},
        headers=headers,
    )
    assert response.status_code == 201

    list_resp = await test_client.get("/subjects", headers=headers)
    assert list_resp.status_code == 200
    subjects = list_resp.json()
    assert len(subjects) >= 1
    found = [s for s in subjects if s["code"] == "ADS"]
    assert len(found) == 1
    assert found[0]["teacher_name"] == "Jan Novak"


@pytest.mark.asyncio
async def test_create_schedule_lessons_generated(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@sched.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Sched",
    )
    headers = await get_auth_header(test_client, "admin@sched.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Sched Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "TestSubj", "code": "TS1", "color": "#FF0000"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    sched_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B213",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    assert sched_resp.status_code == 201
    entry_id = sched_resp.json()["id"]

    result = await db_session.execute(
        select(Lesson).where(Lesson.schedule_entry_id == entry_id)
    )
    lessons = result.scalars().all()
    assert len(lessons) == 13


@pytest.mark.asyncio
async def test_create_schedule_adds_attendance_for_enrolled_students(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@sched-enrolled.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Sched",
    )
    headers = await get_auth_header(
        test_client, "admin@sched-enrolled.sk", "pass"
    )

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Sched Enrolled Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "EnrolledSubj", "code": "ES1", "color": "#FF0000"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "190000001",
            "first_name": "Existing",
            "last_name": "Student",
        },
        headers=headers,
    )

    sched_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B213",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    assert sched_resp.status_code == 201
    entry_id = sched_resp.json()["id"]

    lessons_result = await db_session.execute(
        select(Lesson).where(Lesson.schedule_entry_id == entry_id)
    )
    lesson_ids = [lesson.id for lesson in lessons_result.scalars().all()]
    records_result = await db_session.execute(
        select(AttendanceRecord).where(AttendanceRecord.lesson_id.in_(lesson_ids))
    )
    assert len(records_result.scalars().all()) == 13


@pytest.mark.asyncio
async def test_update_schedule_entry_changes_fields_and_reconciles_lessons(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@sched-update.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Sched",
    )
    headers = await get_auth_header(test_client, "admin@sched-update.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Sched Update Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "UpdateSubj", "code": "US1", "color": "#FF0000"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    sched_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B213",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    entry_id = sched_resp.json()["id"]

    await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "191000001",
            "first_name": "Enrolled",
            "last_name": "Student",
        },
        headers=headers,
    )

    update_resp = await test_client.put(
        f"/semesters/{semester_id}/schedule/{entry_id}",
        json={
            "subject_name": "UpdatedSubj",
            "subject_color": "#00AA00",
            "day_of_week": 2,
            "start_time": "11:00",
            "end_time": "12:30",
            "room": "C101",
            "lesson_type": "laboratorium",
            "is_one_time": False,
            "recurrence_interval": 2,
            "end_date": None,
        },
        headers=headers,
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["subject_name"] == "UpdatedSubj"
    assert body["subject_color"] == "#00AA00"
    assert body["day_of_week"] == 2
    assert body["start_time"] == "11:00"
    assert body["end_time"] == "12:30"
    assert body["room"] == "C101"
    assert body["lesson_type"] == "laboratorium"
    assert body["recurrence_interval"] == 2

    lessons_result = await db_session.execute(
        select(Lesson).where(Lesson.schedule_entry_id == entry_id)
    )
    lessons = lessons_result.scalars().all()
    assert len(lessons) == 7
    assert sorted(lesson.week_number for lesson in lessons) == [
        1, 3, 5, 7, 9, 11, 13,
    ]

    records_result = await db_session.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.lesson_id.in_([lesson.id for lesson in lessons])
        )
    )
    assert len(records_result.scalars().all()) == 7

    second_update_resp = await test_client.put(
        f"/semesters/{semester_id}/schedule/{entry_id}",
        json={
            "subject_name": "UpdatedSubj",
            "subject_color": "#00AA00",
            "day_of_week": 2,
            "start_time": "11:00",
            "end_time": "12:30",
            "room": "C101",
            "lesson_type": "laboratorium",
            "is_one_time": False,
            "recurrence_interval": 1,
            "end_date": None,
        },
        headers=headers,
    )
    assert second_update_resp.status_code == 200

    lessons_result = await db_session.execute(
        select(Lesson).where(Lesson.schedule_entry_id == entry_id)
    )
    lessons = lessons_result.scalars().all()
    assert len(lessons) == 13
    assert sorted(lesson.week_number for lesson in lessons) == [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
    ]


@pytest.mark.asyncio
async def test_get_schedule_calendar_data(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@cal.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Cal",
    )
    headers = await get_auth_header(test_client, "admin@cal.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Cal Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "CalSubj", "code": "CS1", "color": "#00FF00"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B213",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )

    sched_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule", headers=headers
    )
    assert sched_resp.status_code == 200
    entries = sched_resp.json()
    assert len(entries) == 1
    entry = entries[0]
    assert "id" in entry
    assert entry["subject_id"] == subject_id
    assert entry["subject_name"] == "CalSubj"
    assert entry["subject_code"] == "CS1"
    assert entry["subject_color"] == "#00FF00"
    assert entry["day_of_week"] == 1
    assert entry["start_time"] == "09:00"
    assert entry["end_time"] == "10:40"
    assert entry["room"] == "B213"
    assert entry["lesson_type"] == "cvicenie"


@pytest.mark.asyncio
async def test_delete_schedule_cascade(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@del.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Del",
    )
    headers = await get_auth_header(test_client, "admin@del.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Del Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "DelSubj", "code": "DS1", "color": "#0000FF"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    sched_resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B213",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    entry_id = sched_resp.json()["id"]

    del_resp = await test_client.delete(
        f"/semesters/{semester_id}/schedule/{entry_id}", headers=headers
    )
    assert del_resp.status_code == 200

    list_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule", headers=headers
    )
    assert list_resp.json() == []

    result = await db_session.execute(
        select(Lesson).where(Lesson.schedule_entry_id == entry_id)
    )
    assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_delete_semester_removes_related_subject_and_blocks_import(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@del-sem-subj.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="DelSemSubj",
    )
    headers = await get_auth_header(
        test_client, "admin@del-sem-subj.sk", "pass"
    )

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Delete Subject Semester",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "Delete With Semester", "code": "DWS", "color": "#123456"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B213",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    import_resp = await test_client.post(
        f"/subjects/{subject_id}/students/import",
        files={
            "file": (
                "students.csv",
                io.BytesIO(b"ISIC,Meno,Priezvisko\n920000001,Delete,Student\n"),
                "text/csv",
            )
        },
        headers=headers,
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["imported"] == 1

    del_resp = await test_client.delete(
        f"/semesters/{semester_id}", headers=headers
    )
    assert del_resp.status_code == 200

    subject_result = await db_session.execute(
        select(Subject).where(Subject.id == subject_id)
    )
    assert subject_result.scalar_one_or_none() is None

    enrollment_result = await db_session.execute(
        select(Enrollment).where(Enrollment.subject_id == subject_id)
    )
    assert len(enrollment_result.scalars().all()) == 0

    stale_import_resp = await test_client.post(
        f"/subjects/{subject_id}/students/import",
        files={
            "file": (
                "students.csv",
                io.BytesIO(b"ISIC,Meno,Priezvisko\n920000002,Stale,Student\n"),
                "text/csv",
            )
        },
        headers=headers,
    )
    assert stale_import_resp.status_code == 404


@pytest.mark.asyncio
async def test_update_week_note(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@wk.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Wk",
    )
    headers = await get_auth_header(test_client, "admin@wk.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Wk Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    patch_resp = await test_client.patch(
        f"/semesters/{semester_id}/weeks/2",
        json={"note": "Skuska prvy termin"},
        headers=headers,
    )
    assert patch_resp.status_code == 200

    weeks_resp = await test_client.get(
        f"/semesters/{semester_id}/weeks", headers=headers
    )
    weeks = weeks_resp.json()
    week2 = [w for w in weeks if w["week_number"] == 2]
    assert len(week2) == 1
    assert week2[0]["note"] == "Skuska prvy termin"


@pytest.mark.asyncio
async def test_teacher_subject_isolation(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@iso.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Iso",
    )
    await create_test_user(
        db_session, "t1@iso.sk", "pass",
        first_name="Teacher", last_name="One",
    )
    await create_test_user(
        db_session, "t2@iso.sk", "pass",
        first_name="Teacher", last_name="Two",
    )

    h1 = await get_auth_header(test_client, "t1@iso.sk", "pass")
    h2 = await get_auth_header(test_client, "t2@iso.sk", "pass")
    h_admin = await get_auth_header(test_client, "admin@iso.sk", "pass")

    await test_client.post(
        "/subjects",
        json={"name": "Subj T1", "code": "T1S", "color": "#111111"},
        headers=h1,
    )
    await test_client.post(
        "/subjects",
        json={"name": "Subj T2", "code": "T2S", "color": "#222222"},
        headers=h2,
    )

    r1 = await test_client.get("/subjects", headers=h1)
    subjects1 = r1.json()
    assert len(subjects1) == 1
    assert subjects1[0]["code"] == "T1S"

    r2 = await test_client.get("/subjects", headers=h2)
    subjects2 = r2.json()
    assert len(subjects2) == 1
    assert subjects2[0]["code"] == "T2S"

    r_admin = await test_client.get("/subjects", headers=h_admin)
    admin_subjects = r_admin.json()
    assert len(admin_subjects) == 2


@pytest.mark.asyncio
async def test_date_computation_week3(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@date.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Date",
    )
    headers = await get_auth_header(test_client, "admin@date.sk", "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Date Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "DateSubj", "code": "DT1", "color": "#AAAAAA"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "A1",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )

    result = await db_session.execute(
        select(Lesson).order_by(Lesson.week_number)
    )
    lessons = result.scalars().all()

    week1 = [les for les in lessons if les.week_number == 1]
    assert len(week1) == 1
    assert week1[0].date == date(2026, 2, 16)

    week3 = [les for les in lessons if les.week_number == 3]
    assert len(week3) == 1
    assert week3[0].date == date(2026, 3, 2)

    week13 = [les for les in lessons if les.week_number == 13]
    assert len(week13) == 1
    assert week13[0].date == date(2026, 5, 11)


@pytest.mark.asyncio
async def test_openapi_schema_endpoints(test_client: AsyncClient) -> None:
    response = await test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]

    assert "/semesters" in paths
    assert "/subjects" in paths
    assert "/semesters/{semester_id}/schedule" in paths
    assert "/semesters/{semester_id}/weeks" in paths
    assert "/semesters/{semester_id}/weeks/{week_number}" in paths

    all_tags = set()
    for path_ops in paths.values():
        for op in path_ops.values():
            if isinstance(op, dict) and "tags" in op:
                all_tags.update(op["tags"])

    assert "semesters" in all_tags
    assert "subjects" in all_tags
    assert "schedule" in all_tags
    assert "weeks" in all_tags
