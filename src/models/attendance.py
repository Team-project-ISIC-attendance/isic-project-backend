import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class AttendanceStatus(enum.Enum):
    pritomny = "pritomny"
    nepritomny = "nepritomny"
    nahrada = "nahrada"


class MarkedBy(enum.Enum):
    scan = "scan"
    manual = "manual"


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("lesson_id", "isic_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id"), nullable=False, index=True
    )
    isic_id: Mapped[int] = mapped_column(
        ForeignKey("isics.id"), nullable=False, index=True
    )
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.nepritomny
    )
    scan_id: Mapped[int | None] = mapped_column(
        ForeignKey("isic_scans.id"), nullable=True
    )
    marked_by: Mapped[MarkedBy] = mapped_column(
        Enum(MarkedBy), nullable=False, default=MarkedBy.manual
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(UTC),
    )

    lesson: Mapped["Lesson"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Lesson", back_populates="attendance_records"
    )
    isic: Mapped["ISIC"] = relationship("ISIC")  # type: ignore[name-defined]  # noqa: F821
    scan: Mapped["ISICScan | None"] = relationship("ISICScan")  # type: ignore[name-defined]  # noqa: F821
