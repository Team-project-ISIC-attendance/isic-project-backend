"""ISIC scan database model."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class ISICScan(Base):
    """ISIC scan model."""

    __tablename__ = "isic_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    isic_identifier: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

