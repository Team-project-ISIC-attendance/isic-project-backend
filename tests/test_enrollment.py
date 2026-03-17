import io

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.attendance import AttendanceRecord, AttendanceStatus, MarkedBy
from src.models.isic import ISIC
from src.models.user import UserRole
from tests.test_auth import create_test_user, get_auth_header


async def _create_subject_with_lessons(
    client: AsyncClient,
    headers: dict[str, str],
    subject_code: str = "ENR1",
) -> tuple[int, int, int]:
    """Create semester + subject + schedule entry (generates 13 lessons).

    Returns (semester_id, subject_id, schedule_entry_id).
    """
    sem_resp = await client.post(
        "/semesters",
        json={
            "name": "Enroll Sem",
            "start_date": "2026-02-16",
            "end_date": "2026-05-16",
            "total_weeks": 13,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await client.post(
        "/subjects",
        json={"name": "EnrollSubj", "code": subject_code, "color": "#FF0000"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    sched_resp = await client.post(
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

    return semester_id, subject_id, entry_id


@pytest.mark.asyncio
async def test_enroll_student_visible(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@enr1.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Enr",
    )
    headers = await get_auth_header(test_client, "admin@enr1.sk", "pass")
    _, subject_id, _ = await _create_subject_with_lessons(
        test_client, headers, "E01"
    )

    enroll_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "111111111",
            "first_name": "Tobias",
            "last_name": "Banicka",
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201
    body = enroll_resp.json()
    assert "enrollment_id" in body
    assert "isic_id" in body
    assert body["isic_identifier"] == "111111111"
    assert body["first_name"] == "Tobias"
    assert body["last_name"] == "Banicka"
    assert "enrolled_at" in body

    list_resp = await test_client.get(
        f"/subjects/{subject_id}/students", headers=headers
    )
    assert list_resp.status_code == 200
    students = list_resp.json()
    assert len(students) == 1
    assert students[0]["isic_identifier"] == "111111111"
    assert students[0]["first_name"] == "Tobias"
    assert students[0]["last_name"] == "Banicka"


@pytest.mark.asyncio
async def test_enroll_attendance_backfill(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@enr2.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Enr2",
    )
    headers = await get_auth_header(test_client, "admin@enr2.sk", "pass")
    _, subject_id, _ = await _create_subject_with_lessons(
        test_client, headers, "E02"
    )

    enroll_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "222222222",
            "first_name": "Jana",
            "last_name": "Novakova",
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201
    isic_id = enroll_resp.json()["isic_id"]

    result = await db_session.execute(
        select(AttendanceRecord).where(AttendanceRecord.isic_id == isic_id)
    )
    records = result.scalars().all()
    assert len(records) == 13
    for record in records:
        assert record.status == AttendanceStatus.nepritomny
        assert record.marked_by == MarkedBy.manual


@pytest.mark.asyncio
async def test_duplicate_enrollment_conflict(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@enr3.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Enr3",
    )
    headers = await get_auth_header(test_client, "admin@enr3.sk", "pass")
    _, subject_id, _ = await _create_subject_with_lessons(
        test_client, headers, "E03"
    )

    first_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "333333333",
            "first_name": "Peter",
            "last_name": "Kovac",
        },
        headers=headers,
    )
    assert first_resp.status_code == 201

    second_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "333333333",
            "first_name": "Peter",
            "last_name": "Kovac",
        },
        headers=headers,
    )
    assert second_resp.status_code == 409


@pytest.mark.asyncio
async def test_import_csv_three_students(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@enr4.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Enr4",
    )
    headers = await get_auth_header(test_client, "admin@enr4.sk", "pass")
    _, subject_id, _ = await _create_subject_with_lessons(
        test_client, headers, "E04"
    )

    csv_content = (
        "isic_identifier,first_name,last_name\n"
        "444444441,Anna,Horvathova\n"
        "444444442,Martin,Polak\n"
        "444444443,Eva,Kucerova\n"
    )
    csv_file = io.BytesIO(csv_content.encode("utf-8"))

    import_resp = await test_client.post(
        f"/subjects/{subject_id}/students/import",
        files={"file": ("students.csv", csv_file, "text/csv")},
        headers=headers,
    )
    assert import_resp.status_code == 200
    body = import_resp.json()
    assert body["imported"] == 3
    assert body["skipped"] == 0
    assert body["errors"] == []

    list_resp = await test_client.get(
        f"/subjects/{subject_id}/students", headers=headers
    )
    students = list_resp.json()
    assert len(students) == 3

    identifiers = {s["isic_identifier"] for s in students}
    assert identifiers == {"444444441", "444444442", "444444443"}

    for student in students:
        result = await db_session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.isic_id == student["isic_id"]
            )
        )
        records = result.scalars().all()
        assert len(records) == 13


@pytest.mark.asyncio
async def test_import_csv_bad_row(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@enr5.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Enr5",
    )
    headers = await get_auth_header(test_client, "admin@enr5.sk", "pass")
    _, subject_id, _ = await _create_subject_with_lessons(
        test_client, headers, "E05"
    )

    csv_content = (
        "isic_identifier,first_name,last_name\n"
        "555555551,Good,Student\n"
        ",Missing,Identifier\n"
        "555555553,Also,Good\n"
    )
    csv_file = io.BytesIO(csv_content.encode("utf-8"))

    import_resp = await test_client.post(
        f"/subjects/{subject_id}/students/import",
        files={"file": ("students.csv", csv_file, "text/csv")},
        headers=headers,
    )
    assert import_resp.status_code == 200
    body = import_resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row"] == 2
    assert "Missing ISIC identifier" in body["errors"][0]["reason"]


@pytest.mark.asyncio
async def test_import_csv_windows1250(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@enr6.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Enr6",
    )
    headers = await get_auth_header(test_client, "admin@enr6.sk", "pass")
    _, subject_id, _ = await _create_subject_with_lessons(
        test_client, headers, "E06"
    )

    csv_text = (
        "ISIC;Meno;Priezvisko\n"
        "666666661;\u013dubom\u00edr;Kov\u00e1\u010d\n"
        "666666662;M\u00e1ria;Str\u00e1\u017e\n"
    )
    csv_bytes = csv_text.encode("windows-1250")
    csv_file = io.BytesIO(csv_bytes)

    import_resp = await test_client.post(
        f"/subjects/{subject_id}/students/import",
        files={"file": ("students.csv", csv_file, "text/csv")},
        headers=headers,
    )
    assert import_resp.status_code == 200
    body = import_resp.json()
    assert body["imported"] == 2
    assert body["errors"] == []

    list_resp = await test_client.get(
        f"/subjects/{subject_id}/students", headers=headers
    )
    students = list_resp.json()
    names = {s["first_name"] for s in students}
    assert "\u013dubom\u00edr" in names
    assert "M\u00e1ria" in names

    last_names = {s["last_name"] for s in students}
    assert "Kov\u00e1\u010d" in last_names
    assert "Str\u00e1\u017e" in last_names


@pytest.mark.asyncio
async def test_delete_enrollment_cleanup(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@enr7.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Enr7",
    )
    headers = await get_auth_header(test_client, "admin@enr7.sk", "pass")
    _, subject_id, _ = await _create_subject_with_lessons(
        test_client, headers, "E07"
    )

    enroll_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "777777777",
            "first_name": "Delete",
            "last_name": "Me",
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201
    enrollment_id = enroll_resp.json()["enrollment_id"]
    isic_id = enroll_resp.json()["isic_id"]

    result = await db_session.execute(
        select(AttendanceRecord).where(AttendanceRecord.isic_id == isic_id)
    )
    assert len(result.scalars().all()) == 13

    del_resp = await test_client.delete(
        f"/subjects/{subject_id}/students/{enrollment_id}",
        headers=headers,
    )
    assert del_resp.status_code == 200

    list_resp = await test_client.get(
        f"/subjects/{subject_id}/students", headers=headers
    )
    assert list_resp.json() == []

    result = await db_session.execute(
        select(AttendanceRecord).where(AttendanceRecord.isic_id == isic_id)
    )
    assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_enroll_existing_isic(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@enr8.sk", "pass", role=UserRole.admin,
        first_name="Admin", last_name="Enr8",
    )
    headers = await get_auth_header(test_client, "admin@enr8.sk", "pass")
    _, subject_id, _ = await _create_subject_with_lessons(
        test_client, headers, "E08"
    )

    existing_isic = ISIC(isic_identifier="888888888")
    db_session.add(existing_isic)
    await db_session.commit()
    await db_session.refresh(existing_isic)
    original_isic_id = existing_isic.id

    enroll_resp = await test_client.post(
        f"/subjects/{subject_id}/students",
        json={
            "isic_identifier": "888888888",
            "first_name": "Linked",
            "last_name": "Student",
        },
        headers=headers,
    )
    assert enroll_resp.status_code == 201
    body = enroll_resp.json()
    assert body["isic_id"] == original_isic_id
    assert body["first_name"] == "Linked"
    assert body["last_name"] == "Student"


@pytest.mark.asyncio
async def test_enrollment_requires_auth(test_client: AsyncClient) -> None:
    get_resp = await test_client.get("/subjects/1/students")
    assert get_resp.status_code == 401

    post_resp = await test_client.post(
        "/subjects/1/students",
        json={
            "isic_identifier": "999999999",
            "first_name": "No",
            "last_name": "Auth",
        },
    )
    assert post_resp.status_code == 401

    del_resp = await test_client.delete("/subjects/1/students/1")
    assert del_resp.status_code == 401


@pytest.mark.asyncio
async def test_openapi_schema(test_client: AsyncClient) -> None:
    response = await test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]

    assert "/subjects/{subject_id}/students" in paths
    assert "/subjects/{subject_id}/students/import" in paths

    all_tags: set[str] = set()
    for path_ops in paths.values():
        for op in path_ops.values():
            if isinstance(op, dict) and "tags" in op:
                all_tags.update(op["tags"])

    assert "students" in all_tags
