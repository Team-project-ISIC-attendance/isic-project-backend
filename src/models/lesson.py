from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("schedule_entry_id", "week_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    schedule_entry_id: Mapped[int] = mapped_column(
        ForeignKey("schedule_entries.id"), nullable=False, index=True
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    schedule_entry: Mapped["ScheduleEntry"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ScheduleEntry", back_populates="lessons"
    )
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "AttendanceRecord", back_populates="lesson"
    )
