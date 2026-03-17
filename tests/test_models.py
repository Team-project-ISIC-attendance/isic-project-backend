import asyncio
import tempfile
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.attendance import AttendanceRecord, AttendanceStatus, MarkedBy
from src.models.enrollment import Enrollment
from src.models.isic import ISIC
from src.models.lesson import Lesson
from src.models.scan import ISICScan
from src.models.schedule_entry import LessonType, ScheduleEntry
from src.models.semester import Semester
from src.models.subject import Subject
from src.models.user import User, UserRole
from src.models.week_note import WeekNote

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATABASE_FILE_SUFFIX = ".db"
PRE_MIGRATION_REVISION = "b2c3d4e5f6a7"

NEW_TABLES = frozenset({
    "users",
    "semesters",
    "subjects",
    "schedule_entries",
    "week_notes",
    "lessons",
    "enrollments",
    "attendance_records",
})
EXISTING_TABLES = frozenset({"isics", "isic_scans"})
ALL_DOMAIN_TABLES = NEW_TABLES | EXISTING_TABLES


def _alembic_cfg(db_path: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    cfg.set_main_option(
        "script_location", str(BACKEND_DIR / "migrations")
    )
    return cfg


def _sync_engine(db_path: str) -> Engine:
    return create_engine(f"sqlite:///{db_path}")


def _get_table_names(db_path: str) -> set[str]:
    engine = _sync_engine(db_path)
    names = set(inspect(engine).get_table_names())
    engine.dispose()
    return names


@pytest.mark.asyncio
async def test_migration_fresh_db() -> None:
    """Apply all migrations on a fresh DB; verify every domain table exists."""
    with tempfile.NamedTemporaryFile(
        suffix=DATABASE_FILE_SUFFIX, delete=False
    ) as f:
        db_path = f.name

    try:
        await asyncio.to_thread(
            command.upgrade, _alembic_cfg(db_path), "head"
        )
        table_names = _get_table_names(db_path)

        for table in ALL_DOMAIN_TABLES:
            assert table in table_names, f"Table '{table}' missing"
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_migration_existing_db() -> None:
    """Seed ISIC/ISICScan data, apply new migration, verify data intact."""
    with tempfile.NamedTemporaryFile(
        suffix=DATABASE_FILE_SUFFIX, delete=False
    ) as f:
        db_path = f.name

    try:
        cfg = _alembic_cfg(db_path)
        await asyncio.to_thread(
            command.upgrade, cfg, PRE_MIGRATION_REVISION
        )

        engine = _sync_engine(db_path)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO isics (isic_identifier, created_at) "
                    "VALUES (:ident, :ts)"
                ),
                {"ident": "EXISTING001", "ts": datetime.now(UTC).isoformat()},
            )
            conn.execute(
                text(
                    "INSERT INTO isic_scans (isic_id, timestamp, created_at) "
                    "VALUES (1, :ts, :ts)"
                ),
                {"ts": datetime.now(UTC).isoformat()},
            )
        engine.dispose()

        await asyncio.to_thread(command.upgrade, cfg, "head")

        engine = _sync_engine(db_path)
        with engine.connect() as conn:
            isics = (
                conn.execute(text("SELECT * FROM isics")).mappings().fetchall()
            )
            scans = (
                conn.execute(text("SELECT * FROM isic_scans"))
                .mappings()
                .fetchall()
            )
        engine.dispose()

        assert len(isics) == 1
        assert isics[0]["isic_identifier"] == "EXISTING001"
        assert len(scans) == 1

        for table in NEW_TABLES:
            assert table in _get_table_names(db_path), (
                f"Table '{table}' missing"
            )
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_migration_rollback() -> None:
    """Upgrade head, downgrade -1; new tables drop, old ones stay."""
    with tempfile.NamedTemporaryFile(
        suffix=DATABASE_FILE_SUFFIX, delete=False
    ) as f:
        db_path = f.name

    try:
        cfg = _alembic_cfg(db_path)
        await asyncio.to_thread(command.upgrade, cfg, "head")

        tables_after_up = _get_table_names(db_path)
        for t in ALL_DOMAIN_TABLES:
            assert t in tables_after_up

        await asyncio.to_thread(command.downgrade, cfg, "-1")

        tables_after_down = _get_table_names(db_path)
        for t in NEW_TABLES:
            assert t not in tables_after_down, f"'{t}' should be dropped"
        for t in EXISTING_TABLES:
            assert t in tables_after_down, f"'{t}' should survive"
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_fk_relationships(db_session: AsyncSession) -> None:
    """Insert a full object chain and verify join queries work."""
    teacher = User(
        email="fk_teacher@test.com",
        hashed_password="hashed",
        first_name="Test",
        last_name="Teacher",
        role=UserRole.teacher,
    )
    db_session.add(teacher)
    await db_session.flush()

    semester = Semester(
        name="25/26 LS",
        start_date=date(2026, 2, 9),
        end_date=date(2026, 5, 15),
    )
    db_session.add(semester)
    await db_session.flush()

    subject = Subject(
        name="Algoritmy",
        code="ALG01",
        teacher_id=teacher.id,
    )
    db_session.add(subject)
    await db_session.flush()

    entry = ScheduleEntry(
        subject_id=subject.id,
        semester_id=semester.id,
        day_of_week=1,
        start_time=time(9, 0),
        end_time=time(10, 40),
        room="B213",
        lesson_type=LessonType.cvicenie,
    )
    db_session.add(entry)
    await db_session.flush()

    lesson = Lesson(
        schedule_entry_id=entry.id,
        week_number=1,
        date=date(2026, 2, 10),
    )
    db_session.add(lesson)
    await db_session.flush()

    isic = ISIC(isic_identifier="FK_STUDENT001")
    db_session.add(isic)
    await db_session.flush()

    scan = ISICScan(isic_id=isic.id)
    db_session.add(scan)
    await db_session.flush()

    enrollment = Enrollment(subject_id=subject.id, isic_id=isic.id)
    db_session.add(enrollment)
    await db_session.flush()

    record = AttendanceRecord(
        lesson_id=lesson.id,
        isic_id=isic.id,
        status=AttendanceStatus.pritomny,
        scan_id=scan.id,
        marked_by=MarkedBy.scan,
    )
    db_session.add(record)
    await db_session.flush()

    await db_session.refresh(subject, ["teacher"])
    assert subject.teacher.email == "fk_teacher@test.com"

    await db_session.refresh(entry, ["subject", "semester"])
    assert entry.subject.code == "ALG01"
    assert entry.semester.name == "25/26 LS"

    await db_session.refresh(lesson, ["schedule_entry"])
    assert lesson.schedule_entry.room == "B213"

    await db_session.refresh(enrollment, ["subject", "isic"])
    assert enrollment.subject.code == "ALG01"
    assert enrollment.isic.isic_identifier == "FK_STUDENT001"

    await db_session.refresh(record, ["lesson", "isic", "scan"])
    assert record.lesson.week_number == 1
    assert record.isic.isic_identifier == "FK_STUDENT001"
    assert record.scan is not None
    assert record.scan.id == scan.id


@pytest.mark.asyncio
async def test_unique_constraints(db_session: AsyncSession) -> None:
    """Every unique / composite-unique constraint must reject duplicates."""

    async def _make_teacher(email: str) -> User:
        u = User(
            email=email,
            hashed_password="h",
            first_name="T",
            last_name="T",
        )
        db_session.add(u)
        await db_session.flush()
        return u

    async def _make_semester(name: str) -> Semester:
        s = Semester(
            name=name,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 5, 1),
        )
        db_session.add(s)
        await db_session.flush()
        return s

    async def _make_subject(code: str, teacher: User) -> Subject:
        s = Subject(
            name=f"Subj-{code}", code=code, teacher_id=teacher.id
        )
        db_session.add(s)
        await db_session.flush()
        return s

    async def _make_entry(
        subject: Subject, semester: Semester
    ) -> ScheduleEntry:
        e = ScheduleEntry(
            subject_id=subject.id,
            semester_id=semester.id,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 40),
            lesson_type=LessonType.prednaska,
        )
        db_session.add(e)
        await db_session.flush()
        return e

    teacher = await _make_teacher("uc@test.com")

    # User.email
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                User(
                    email="uc@test.com",
                    hashed_password="h",
                    first_name="X",
                    last_name="X",
                )
            )
            await db_session.flush()

    # Semester.name
    sem = await _make_semester("UC-SEM")

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Semester(
                    name="UC-SEM",
                    start_date=date(2026, 9, 1),
                    end_date=date(2026, 12, 1),
                )
            )
            await db_session.flush()

    # Subject.code
    sub = await _make_subject("UC01", teacher)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Subject(
                    name="Other",
                    code="UC01",
                    teacher_id=teacher.id,
                )
            )
            await db_session.flush()

    # WeekNote(semester_id, week_number)
    db_session.add(WeekNote(semester_id=sem.id, week_number=1, note="n"))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                WeekNote(semester_id=sem.id, week_number=1, note="dup")
            )
            await db_session.flush()

    # Lesson(schedule_entry_id, week_number)
    entry = await _make_entry(sub, sem)
    db_session.add(
        Lesson(
            schedule_entry_id=entry.id,
            week_number=1,
            date=date(2026, 2, 9),
        )
    )
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Lesson(
                    schedule_entry_id=entry.id,
                    week_number=1,
                    date=date(2026, 2, 9),
                )
            )
            await db_session.flush()

    # Enrollment(subject_id, isic_id)
    isic = ISIC(isic_identifier="UC_ISIC001")
    db_session.add(isic)
    await db_session.flush()

    db_session.add(Enrollment(subject_id=sub.id, isic_id=isic.id))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Enrollment(subject_id=sub.id, isic_id=isic.id)
            )
            await db_session.flush()

    # AttendanceRecord(lesson_id, isic_id)
    les = Lesson(
        schedule_entry_id=entry.id,
        week_number=2,
        date=date(2026, 2, 16),
    )
    db_session.add(les)
    await db_session.flush()

    db_session.add(AttendanceRecord(lesson_id=les.id, isic_id=isic.id))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                AttendanceRecord(lesson_id=les.id, isic_id=isic.id)
            )
            await db_session.flush()
