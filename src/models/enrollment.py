from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("subject_id", "isic_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id"), nullable=False, index=True
    )
    isic_id: Mapped[int] = mapped_column(
        ForeignKey("isics.id"), nullable=False, index=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    subject: Mapped["Subject"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Subject", back_populates="enrollments"
    )
    isic: Mapped["ISIC"] = relationship("ISIC")  # type: ignore[name-defined]  # noqa: F821
