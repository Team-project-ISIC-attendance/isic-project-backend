from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class HardwareDevice(Base):
    __tablename__ = "hardware_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    base_topic: Mapped[str] = mapped_column(String, nullable=False, default="device")
    teacher_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    location_id: Mapped[str | None] = mapped_column(String, nullable=True)
    firmware: Mapped[str | None] = mapped_column(String, nullable=True)
    health_state: Mapped[str | None] = mapped_column(String, nullable=True)
    health_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    metrics_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    config_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attendance_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_metrics_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_config_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    scans: Mapped[list["ISICScan"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ISICScan", back_populates="hardware_device"
    )
    teacher: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="hardware_devices"
    )
    pairing_sessions: Mapped[list["DevicePairingSession"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DevicePairingSession", back_populates="hardware_device"
    )
