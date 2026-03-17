from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class WeekNote(Base):
    __tablename__ = "week_notes"
    __table_args__ = (UniqueConstraint("semester_id", "week_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id"), nullable=False, index=True
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String, nullable=False, default="")

    semester: Mapped["Semester"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Semester", back_populates="week_notes"
    )
