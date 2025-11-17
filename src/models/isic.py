from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class ISIC(Base):
    __tablename__ = "isics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    isic_identifier: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    scans: Mapped[list["ISICScan"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ISICScan", back_populates="isic"
    )

