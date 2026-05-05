from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_mqtt_client
from src.api.schemas import (
    ConfigRequestPayload,
    HardwareCommandResponse,
    HardwareDeviceDetailResponse,
    HardwareDeviceSummaryResponse,
    HardwareSnapshotResponse,
    PairingSessionResponse,
)
from src.database.connection import get_db
from src.models.hardware_device import HardwareDevice
from src.models.user import User, UserRole
from src.mqtt.client import MQTTClient
from src.services.hardware_service import (
    CONFIG_SECTION_KEYS,
    build_device_topic,
    can_access_device,
    get_hardware_device,
    get_pairing_session_for_teacher,
    list_hardware_devices,
    list_hardware_devices_for_user,
    list_unclaimed_hardware_devices,
    release_device_claim,
    start_device_pairing_session,
)
from src.utils.datetime import isoformat_utc

router = APIRouter(prefix="/hardware/devices", tags=["hardware"])


def _iso_or_none(value: object) -> str | None:
    if isinstance(value, datetime):
        return isoformat_utc(value)
    return None


def _summary_response(
    device: HardwareDevice,
) -> HardwareDeviceSummaryResponse:
    return HardwareDeviceSummaryResponse(
        id=device.id,
        device_id=device.device_id,
        base_topic=device.base_topic,
        teacher_id=device.teacher_id,
        teacher_name=(
            f"{device.teacher.first_name} {device.teacher.last_name}"
            if device.teacher is not None
            else None
        ),
        claimed_at=_iso_or_none(device.claimed_at),
        is_claimed=device.teacher_id is not None,
        location_id=device.location_id,
        firmware=device.firmware,
        health_state=device.health_state,
        last_seen_at=_iso_or_none(device.last_seen_at),
        last_attendance_at=_iso_or_none(device.last_attendance_at),
        last_health_at=_iso_or_none(device.last_health_at),
        last_metrics_at=_iso_or_none(device.last_metrics_at),
        last_config_at=_iso_or_none(device.last_config_at),
    )


def _detail_response(device: HardwareDevice) -> HardwareDeviceDetailResponse:
    return HardwareDeviceDetailResponse(
        **_summary_response(device).model_dump(),
        health_payload=device.health_payload,
        metrics_payload=device.metrics_payload,
        config_payload=device.config_payload,
    )


def _snapshot_response(
    device: HardwareDevice,
    *,
    received_at: object,
    payload: dict[str, Any] | None,
) -> HardwareSnapshotResponse:
    return HardwareSnapshotResponse(
        device_id=device.device_id,
        received_at=_iso_or_none(received_at),
        payload=payload,
    )


def _pairing_response(pairing_session: "DevicePairingSession") -> PairingSessionResponse:  # type: ignore[name-defined]  # noqa: F821
    return PairingSessionResponse(
        device_id=pairing_session.hardware_device.device_id,
        teacher_id=pairing_session.teacher_id,
        teacher_isic_identifier=pairing_session.teacher.isic_identifier or "",
        status=pairing_session.status.value,
        started_at=isoformat_utc(pairing_session.started_at) or "",
        expires_at=isoformat_utc(pairing_session.expires_at) or "",
        completed_at=_iso_or_none(pairing_session.completed_at),
    )


async def _require_device(
    db: AsyncSession,
    device_id: str,
) -> HardwareDevice:
    device = await get_hardware_device(db, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hardware device not found",
        )
    return device


def _ensure_device_access(user: User, device: HardwareDevice) -> None:
    if can_access_device(user, device):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not your device",
    )


@router.get(
    "",
    response_model=list[HardwareDeviceSummaryResponse],
    summary="List hardware devices visible to the current user",
)
async def list_devices(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[HardwareDeviceSummaryResponse]:
    devices = await list_hardware_devices_for_user(db, current_user)
    return [_summary_response(device) for device in devices]


@router.get(
    "/unclaimed",
    response_model=list[HardwareDeviceSummaryResponse],
    summary="List recent unclaimed hardware devices",
)
async def list_unclaimed_devices(
    active_within_minutes: int = Query(10, ge=1, le=1440),
    _: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[HardwareDeviceSummaryResponse]:
    devices = await list_unclaimed_hardware_devices(
        db, active_within_minutes=active_within_minutes
    )
    return [_summary_response(device) for device in devices]


@router.get(
    "/{device_id}",
    response_model=HardwareDeviceDetailResponse,
    summary="Get hardware device detail",
)
async def get_device(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> HardwareDeviceDetailResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    return _detail_response(device)


@router.get(
    "/{device_id}/health",
    response_model=HardwareSnapshotResponse,
    summary="Get latest stored health snapshot",
)
async def get_device_health(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> HardwareSnapshotResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    return _snapshot_response(
        device,
        received_at=device.last_health_at,
        payload=device.health_payload,
    )


@router.get(
    "/{device_id}/metrics",
    response_model=HardwareSnapshotResponse,
    summary="Get latest stored metrics snapshot",
)
async def get_device_metrics(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> HardwareSnapshotResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    return _snapshot_response(
        device,
        received_at=device.last_metrics_at,
        payload=device.metrics_payload,
    )


@router.get(
    "/{device_id}/config",
    response_model=HardwareSnapshotResponse,
    summary="Get latest stored config snapshot",
)
async def get_device_config(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> HardwareSnapshotResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    return _snapshot_response(
        device,
        received_at=device.last_config_at,
        payload=device.config_payload,
    )


@router.post(
    "/{device_id}/health/request",
    response_model=HardwareCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request an immediate health publish from the board",
)
async def request_device_health(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    mqtt_client: MQTTClient = Depends(get_mqtt_client),  # noqa: B008
) -> HardwareCommandResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    topic = build_device_topic(device, "health", "request")
    await mqtt_client.publish(topic, b"")
    return HardwareCommandResponse(detail="Health request published", topic=topic)


@router.post(
    "/{device_id}/metrics/request",
    response_model=HardwareCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request an immediate metrics publish from the board",
)
async def request_device_metrics(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    mqtt_client: MQTTClient = Depends(get_mqtt_client),  # noqa: B008
) -> HardwareCommandResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    topic = build_device_topic(device, "metrics", "request")
    await mqtt_client.publish(topic, b"")
    return HardwareCommandResponse(
        detail="Metrics request published",
        topic=topic,
    )


@router.post(
    "/{device_id}/config/request",
    response_model=HardwareCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request the full runtime config from the board",
)
async def request_device_config(
    device_id: str,
    section: str | None = Query(None),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    mqtt_client: MQTTClient = Depends(get_mqtt_client),  # noqa: B008
) -> HardwareCommandResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    if section is not None and section not in CONFIG_SECTION_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported config section",
        )
    topic_segments = ["config", "get"]
    if section is not None:
        topic_segments.append(section)
    topic = build_device_topic(device, *topic_segments)
    await mqtt_client.publish(topic, b"")
    detail = (
        f"Config section request published for '{section}'"
        if section is not None
        else "Full config request published"
    )
    return HardwareCommandResponse(detail=detail, topic=topic)


@router.put(
    "/{device_id}/config",
    response_model=HardwareCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Publish a full runtime config to the board",
)
async def set_device_config(
    device_id: str,
    body: ConfigRequestPayload,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    mqtt_client: MQTTClient = Depends(get_mqtt_client),  # noqa: B008
) -> HardwareCommandResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    topic = build_device_topic(device, "config", "set")
    await mqtt_client.publish_json(topic, body.root)
    return HardwareCommandResponse(
        detail="Full config published",
        topic=topic,
    )


@router.put(
    "/{device_id}/config/{section}",
    response_model=HardwareCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Publish a single config section to the board",
)
async def set_device_config_section(
    device_id: str,
    section: str,
    body: ConfigRequestPayload,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    mqtt_client: MQTTClient = Depends(get_mqtt_client),  # noqa: B008
) -> HardwareCommandResponse:
    if section not in CONFIG_SECTION_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported config section",
        )
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    topic = build_device_topic(device, "config", "set", section)
    await mqtt_client.publish_json(topic, body.root)
    return HardwareCommandResponse(
        detail=f"Config section '{section}' published",
        topic=topic,
    )


@router.post(
    "/{device_id}/pairing/start",
    response_model=PairingSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start teacher-device pairing by scan",
)
async def start_pairing(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PairingSessionResponse:
    device = await _require_device(db, device_id)
    if current_user.role != UserRole.teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can pair devices",
        )
    try:
        pairing_session = await start_device_pairing_session(
            db, device, current_user
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err
    pairing_session.hardware_device = device
    pairing_session.teacher = current_user
    return _pairing_response(pairing_session)


@router.get(
    "/{device_id}/pairing",
    response_model=PairingSessionResponse | None,
    summary="Get current teacher pairing status for a device",
)
async def get_pairing(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PairingSessionResponse | None:
    pairing_session = await get_pairing_session_for_teacher(
        db, device_id, current_user.id
    )
    if pairing_session is None:
        return None
    return _pairing_response(pairing_session)


@router.delete(
    "/{device_id}/claim",
    response_model=HardwareDeviceDetailResponse,
    summary="Release a claimed device",
)
async def release_claim(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> HardwareDeviceDetailResponse:
    device = await _require_device(db, device_id)
    _ensure_device_access(current_user, device)
    updated = await release_device_claim(db, device)
    return _detail_response(updated)
