import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class DevicePairingStatus(enum.Enum):
    pending = "pending"
    completed = "completed"
    expired = "expired"
    cancelled = "cancelled"


class DevicePairingSession(Base):
    __tablename__ = "device_pairing_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hardware_device_id: Mapped[int] = mapped_column(
        ForeignKey("hardware_devices.id"), nullable=False, index=True
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[DevicePairingStatus] = mapped_column(
        Enum(DevicePairingStatus),
        nullable=False,
        default=DevicePairingStatus.pending,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    hardware_device: Mapped["HardwareDevice"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "HardwareDevice", back_populates="pairing_sessions"
    )
    teacher: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="device_pairing_sessions"
    )
