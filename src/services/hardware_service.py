import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.device_pairing_session import (
    DevicePairingSession,
    DevicePairingStatus,
)
from src.models.hardware_device import HardwareDevice
from src.models.user import User, UserRole
from src.services.scan_service import normalize_isic_identifier
from src.utils.datetime import coerce_utc_datetime

CONFIG_SECTION_KEYS = frozenset({
    "wifi",
    "mqtt",
    "device",
    "pn532",
    "attendance",
    "feedback",
    "health",
    "ota",
    "power",
})


@dataclass(frozen=True)
class ParsedHardwareTopic:
    base_topic: str
    device_id: str
    kind: str
    section: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _coerce_utc(timestamp: datetime | None) -> datetime:
    if timestamp is None:
        return _utc_now()
    return coerce_utc_datetime(timestamp)


def parse_hardware_topic(topic: str) -> ParsedHardwareTopic | None:
    parts = topic.split("/")
    if len(parts) < 3:
        return None

    if parts[-1] in {"attendance", "health", "metrics", "config"}:
        device_index = -2
        kind = parts[-1]
        section = None
    elif len(parts) >= 4 and parts[-2] == "config":
        device_index = -3
        kind = "config"
        section = parts[-1]
    elif len(parts) >= 4 and parts[-2] == "ota":
        device_index = -3
        kind = f"ota/{parts[-1]}"
        section = None
    else:
        return None

    base_topic = "/".join(parts[:device_index])
    device_id = parts[device_index]
    if not base_topic or not device_id:
        return None

    return ParsedHardwareTopic(
        base_topic=base_topic,
        device_id=device_id,
        kind=kind,
        section=section,
    )


async def get_or_create_hardware_device(
    session: AsyncSession,
    base_topic: str,
    device_id: str,
) -> HardwareDevice:
    stmt = select(HardwareDevice).where(HardwareDevice.device_id == device_id)
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    if device is None:
        device = HardwareDevice(device_id=device_id, base_topic=base_topic)
        session.add(device)
        await session.flush()
    elif device.base_topic != base_topic:
        device.base_topic = base_topic

    return device


def update_device_last_seen(
    device: HardwareDevice, timestamp: datetime | None = None
) -> None:
    seen_at = _coerce_utc(timestamp)
    device.last_seen_at = seen_at


def record_device_attendance(
    device: HardwareDevice, timestamp: datetime | None = None
) -> None:
    seen_at = _coerce_utc(timestamp)
    device.last_attendance_at = seen_at
    device.last_seen_at = seen_at


def _json_object(payload: str) -> dict[str, Any]:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object payload")
    return data


def _extract_location_id(config_payload: dict[str, Any]) -> str | None:
    device_section = config_payload.get("device")
    if isinstance(device_section, dict):
        location_id = device_section.get("locationId")
        if isinstance(location_id, str):
            return location_id
    return None


def _merge_config_section(
    existing_config: dict[str, Any] | None,
    section: str,
    section_payload: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing_config or {})
    merged[section] = section_payload
    return merged


def store_health_payload(
    device: HardwareDevice,
    payload: str,
    received_at: datetime | None = None,
) -> None:
    health_payload = _json_object(payload)
    timestamp = _coerce_utc(received_at)

    device.health_payload = health_payload
    device.health_state = (
        health_payload["state"]
        if isinstance(health_payload.get("state"), str)
        else device.health_state
    )
    device.firmware = (
        health_payload["firmware"]
        if isinstance(health_payload.get("firmware"), str)
        else device.firmware
    )
    device.last_health_at = timestamp
    device.last_seen_at = timestamp


def store_metrics_payload(
    device: HardwareDevice,
    payload: str,
    received_at: datetime | None = None,
) -> None:
    metrics_payload = _json_object(payload)
    timestamp = _coerce_utc(received_at)

    device.metrics_payload = metrics_payload
    device.last_metrics_at = timestamp
    device.last_seen_at = timestamp


def store_config_payload(
    device: HardwareDevice,
    payload: str,
    section: str | None,
    received_at: datetime | None = None,
) -> None:
    config_payload = _json_object(payload)
    timestamp = _coerce_utc(received_at)

    if section is None:
        device.config_payload = config_payload
    else:
        if section not in CONFIG_SECTION_KEYS:
            return
        device.config_payload = _merge_config_section(
            device.config_payload,
            section,
            config_payload,
        )

    device.last_config_at = timestamp
    device.last_seen_at = timestamp
    location_id = _extract_location_id(device.config_payload or {})
    if location_id is not None:
        device.location_id = location_id


async def list_hardware_devices(
    session: AsyncSession,
) -> list[HardwareDevice]:
    result = await session.execute(_device_query().order_by(HardwareDevice.device_id))
    return list(result.scalars().all())


def _device_query() -> Select[tuple[HardwareDevice]]:
    return select(HardwareDevice).options(selectinload(HardwareDevice.teacher))


async def list_hardware_devices_for_user(
    session: AsyncSession,
    user: User,
) -> list[HardwareDevice]:
    stmt = _device_query().order_by(HardwareDevice.device_id)
    if user.role != UserRole.admin:
        stmt = stmt.where(HardwareDevice.teacher_id == user.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_unclaimed_hardware_devices(
    session: AsyncSession,
    active_within_minutes: int | None = None,
) -> list[HardwareDevice]:
    stmt = _device_query().where(HardwareDevice.teacher_id.is_(None))
    if active_within_minutes is not None:
        stmt = stmt.where(
            HardwareDevice.last_seen_at
            >= _utc_now() - timedelta(minutes=active_within_minutes)
        )
    result = await session.execute(
        stmt.order_by(HardwareDevice.last_seen_at.desc(), HardwareDevice.device_id)
    )
    return list(result.scalars().all())


async def get_hardware_device(
    session: AsyncSession,
    device_id: str,
) -> HardwareDevice | None:
    result = await session.execute(
        _device_query()
        .where(HardwareDevice.device_id == device_id)
        .options(
            selectinload(HardwareDevice.scans),
            selectinload(HardwareDevice.pairing_sessions),
        )
    )
    return result.scalar_one_or_none()


def can_access_device(user: User, device: HardwareDevice) -> bool:
    return user.role == UserRole.admin or device.teacher_id == user.id


async def expire_stale_pairing_sessions(
    session: AsyncSession,
    current_time: datetime | None = None,
) -> None:
    now = _coerce_utc(current_time)
    result = await session.execute(
        select(DevicePairingSession).where(
            DevicePairingSession.status == DevicePairingStatus.pending
        )
    )
    changed = False
    for pairing_session in result.scalars().all():
        if _coerce_utc(pairing_session.expires_at) < now:
            pairing_session.status = DevicePairingStatus.expired
            changed = True
    if changed:
        await session.flush()


async def start_device_pairing_session(
    session: AsyncSession,
    device: HardwareDevice,
    teacher: User,
    duration_seconds: int = 120,
) -> DevicePairingSession:
    if teacher.role != UserRole.teacher:
        raise ValueError("Only teachers can start a pairing session")
    if teacher.isic_identifier is None:
        raise ValueError("Teacher must set an ISIC identifier before pairing")
    if device.teacher_id is not None and device.teacher_id != teacher.id:
        raise ValueError("Device is already claimed by another teacher")

    now = _utc_now()
    await expire_stale_pairing_sessions(session, now)
    result = await session.execute(
        select(DevicePairingSession).where(
            DevicePairingSession.hardware_device_id == device.id,
            DevicePairingSession.status == DevicePairingStatus.pending,
        )
    )
    active_sessions = result.scalars().all()
    for pairing_session in active_sessions:
        if pairing_session.teacher_id == teacher.id:
            pairing_session.status = DevicePairingStatus.cancelled
        else:
            raise ValueError("Another teacher is already pairing this device")

    pairing_session = DevicePairingSession(
        hardware_device_id=device.id,
        teacher_id=teacher.id,
        status=DevicePairingStatus.pending,
        started_at=now,
        expires_at=now + timedelta(seconds=duration_seconds),
    )
    session.add(pairing_session)
    await session.commit()
    await session.refresh(pairing_session)
    return pairing_session


async def get_pairing_session_for_teacher(
    session: AsyncSession,
    device_id: str,
    teacher_id: int,
) -> DevicePairingSession | None:
    device = await get_hardware_device(session, device_id)
    if device is None:
        return None
    await expire_stale_pairing_sessions(session)
    result = await session.execute(
        select(DevicePairingSession)
        .where(
            DevicePairingSession.hardware_device_id == device.id,
            DevicePairingSession.teacher_id == teacher_id,
        )
        .order_by(DevicePairingSession.started_at.desc())
        .options(
            selectinload(DevicePairingSession.teacher),
            selectinload(DevicePairingSession.hardware_device),
        )
    )
    return result.scalars().first()


async def release_device_claim(
    session: AsyncSession,
    device: HardwareDevice,
) -> HardwareDevice:
    device.teacher_id = None
    device.claimed_at = None
    result = await session.execute(
        select(DevicePairingSession).where(
            DevicePairingSession.hardware_device_id == device.id,
            DevicePairingSession.status == DevicePairingStatus.pending,
        )
    )
    for pairing_session in result.scalars().all():
        pairing_session.status = DevicePairingStatus.cancelled
    await session.commit()
    await session.refresh(device)
    return device


async def claim_device_from_scan(
    session: AsyncSession,
    device: HardwareDevice,
    scanned_identifier: str,
    scanned_at: datetime,
) -> DevicePairingSession | None:
    await expire_stale_pairing_sessions(session, scanned_at)
    normalized_identifier = normalize_isic_identifier(scanned_identifier)
    result = await session.execute(
        select(DevicePairingSession)
        .join(DevicePairingSession.teacher)
        .where(
            DevicePairingSession.hardware_device_id == device.id,
            DevicePairingSession.status == DevicePairingStatus.pending,
            User.isic_identifier == normalized_identifier,
        )
        .order_by(DevicePairingSession.started_at.desc())
        .options(selectinload(DevicePairingSession.teacher))
    )
    pairing_session = result.scalars().first()
    if pairing_session is None:
        return None

    if device.teacher_id is not None and device.teacher_id != pairing_session.teacher_id:
        pairing_session.status = DevicePairingStatus.cancelled
        await session.commit()
        await session.refresh(pairing_session)
        return pairing_session

    completed_at = _coerce_utc(scanned_at)
    device.teacher_id = pairing_session.teacher_id
    device.claimed_at = completed_at
    pairing_session.status = DevicePairingStatus.completed
    pairing_session.completed_at = completed_at

    other_sessions_result = await session.execute(
        select(DevicePairingSession).where(
            DevicePairingSession.hardware_device_id == device.id,
            DevicePairingSession.status == DevicePairingStatus.pending,
            DevicePairingSession.id != pairing_session.id,
        )
    )
    for other_session in other_sessions_result.scalars().all():
        other_session.status = DevicePairingStatus.cancelled

    await session.commit()
    await session.refresh(pairing_session)
    return pairing_session


def build_device_topic(
    device: HardwareDevice,
    *segments: str,
) -> str:
    path = [device.base_topic, device.device_id, *segments]
    return "/".join(path)
