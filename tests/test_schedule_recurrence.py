from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.lesson import Lesson
from src.models.user import UserRole
from tests.test_auth import create_test_user, get_auth_header


async def _setup_semester_and_subject(
    test_client: AsyncClient,
    db_session: AsyncSession,
    email: str = "admin@rec.sk",
    start_date: str = "2026-02-16",
    total_weeks: int = 13,
) -> tuple[dict[str, str], int, int]:
    """Create admin user, semester, and subject. Return (headers, semester_id, subject_id)."""
    await create_test_user(
        db_session, email, "pass", role=UserRole.admin,
        first_name="Admin", last_name="Rec",
    )
    headers = await get_auth_header(test_client, email, "pass")

    sem_resp = await test_client.post(
        "/semesters",
        json={
            "name": "Rec Sem",
            "start_date": start_date,
            "end_date": "2026-05-16",
            "total_weeks": total_weeks,
        },
        headers=headers,
    )
    semester_id = sem_resp.json()["id"]

    subj_resp = await test_client.post(
        "/subjects",
        json={"name": "RecSubj", "code": "RC1", "color": "#FF0000"},
        headers=headers,
    )
    subject_id = subj_resp.json()["id"]

    return headers, semester_id, subject_id


@pytest.mark.asyncio
async def test_one_time_entry_creates_single_lesson(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A one-time schedule entry should create exactly 1 lesson."""
    headers, semester_id, subject_id = await _setup_semester_and_subject(
        test_client, db_session, email="admin@ot1.sk",
    )

    resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "A1",
            "lesson_type": "prednaska",
            "is_one_time": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    result = await db_session.execute(
        select(Lesson).where(Lesson.schedule_entry_id == entry_id)
    )
    lessons = result.scalars().all()
    assert len(lessons) == 1
    assert lessons[0].week_number == 1


@pytest.mark.asyncio
async def test_recurring_interval_2_creates_odd_weeks(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """recurrence_interval=2 should create lessons on weeks 1, 3, 5, 7, 9, 11, 13."""
    headers, semester_id, subject_id = await _setup_semester_and_subject(
        test_client, db_session, email="admin@ri2.sk",
    )

    resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "B1",
            "lesson_type": "cvicenie",
            "recurrence_interval": 2,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    result = await db_session.execute(
        select(Lesson)
        .where(Lesson.schedule_entry_id == entry_id)
        .order_by(Lesson.week_number)
    )
    lessons = result.scalars().all()
    week_numbers = [les.week_number for les in lessons]
    assert week_numbers == [1, 3, 5, 7, 9, 11, 13]


@pytest.mark.asyncio
async def test_recurring_with_end_date(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """end_date should limit lessons to those on or before the given date."""
    headers, semester_id, subject_id = await _setup_semester_and_subject(
        test_client, db_session, email="admin@ed.sk",
    )

    # Semester starts 2026-02-16 (Monday). day_of_week=1 → Mondays.
    # Week 1: 2026-02-16, Week 2: 2026-02-23, Week 3: 2026-03-02, Week 4: 2026-03-09
    # end_date = 2026-03-05 → only weeks 1, 2, 3 (2/16, 2/23, 3/2)
    resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "C1",
            "lesson_type": "prednaska",
            "end_date": "2026-03-05",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    result = await db_session.execute(
        select(Lesson)
        .where(Lesson.schedule_entry_id == entry_id)
        .order_by(Lesson.week_number)
    )
    lessons = result.scalars().all()
    assert len(lessons) == 3
    assert all(les.date <= date(2026, 3, 5) for les in lessons)


@pytest.mark.asyncio
async def test_default_recurrence_creates_13_lessons(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Default params (is_one_time=False, interval=1, no end_date) → 13 lessons."""
    headers, semester_id, subject_id = await _setup_semester_and_subject(
        test_client, db_session, email="admin@def.sk",
    )

    resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "D1",
            "lesson_type": "cvicenie",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    result = await db_session.execute(
        select(Lesson).where(Lesson.schedule_entry_id == entry_id)
    )
    lessons = result.scalars().all()
    assert len(lessons) == 13


@pytest.mark.asyncio
async def test_response_includes_new_fields(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ScheduleEntryResponse should include is_one_time, recurrence_interval, end_date."""
    headers, semester_id, subject_id = await _setup_semester_and_subject(
        test_client, db_session, email="admin@resp.sk",
    )

    resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "E1",
            "lesson_type": "prednaska",
            "is_one_time": True,
            "recurrence_interval": 3,
            "end_date": "2026-04-01",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_one_time"] is True
    assert body["recurrence_interval"] == 3
    assert body["end_date"] == "2026-04-01"

    # Also verify GET endpoint returns the fields
    list_resp = await test_client.get(
        f"/semesters/{semester_id}/schedule", headers=headers
    )
    assert list_resp.status_code == 200
    entries = list_resp.json()
    assert len(entries) >= 1
    entry = entries[0]
    assert "is_one_time" in entry
    assert "recurrence_interval" in entry
    assert "end_date" in entry


@pytest.mark.asyncio
async def test_interval_and_end_date_combined(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """recurrence_interval=2 + end_date should combine both filters."""
    headers, semester_id, subject_id = await _setup_semester_and_subject(
        test_client, db_session, email="admin@comb.sk",
    )

    # Semester starts 2026-02-16 (Monday). day_of_week=1 → Mondays.
    # interval=2 → weeks 1, 3, 5, 7, 9, 11, 13
    # end_date 2026-03-20 → week 1 (2/16), week 3 (3/2), week 5 (3/16)
    # week 7 would be 3/30 which is > 3/20
    resp = await test_client.post(
        f"/semesters/{semester_id}/schedule",
        json={
            "subject_id": subject_id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:40",
            "room": "F1",
            "lesson_type": "laboratorium",
            "recurrence_interval": 2,
            "end_date": "2026-03-20",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    result = await db_session.execute(
        select(Lesson)
        .where(Lesson.schedule_entry_id == entry_id)
        .order_by(Lesson.week_number)
    )
    lessons = result.scalars().all()
    week_numbers = [les.week_number for les in lessons]
    assert week_numbers == [1, 3, 5]
    assert all(les.date <= date(2026, 3, 20) for les in lessons)
