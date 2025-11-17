from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class ISICScan(Base):
    __tablename__ = "isic_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    isic_id: Mapped[int] = mapped_column(
        ForeignKey("isics.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    isic: Mapped["ISIC"] = relationship("ISIC", back_populates="scans")  # type: ignore[name-defined]  # noqa: F821

