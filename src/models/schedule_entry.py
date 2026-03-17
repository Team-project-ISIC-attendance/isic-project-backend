import enum
from datetime import UTC, datetime, time

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class LessonType(enum.Enum):
    prednaska = "prednaska"
    cvicenie = "cvicenie"
    laboratorium = "laboratorium"


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id"), nullable=False, index=True
    )
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    room: Mapped[str | None] = mapped_column(String, nullable=True)
    lesson_type: Mapped[LessonType] = mapped_column(
        Enum(LessonType), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    subject: Mapped["Subject"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Subject", back_populates="schedule_entries"
    )
    semester: Mapped["Semester"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Semester", back_populates="schedule_entries"
    )
    lessons: Mapped[list["Lesson"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Lesson", back_populates="schedule_entry"
    )
