from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Semester(Base):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=13)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    schedule_entries: Mapped[list["ScheduleEntry"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ScheduleEntry", back_populates="semester"
    )
    week_notes: Mapped[list["WeekNote"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "WeekNote", back_populates="semester"
    )
