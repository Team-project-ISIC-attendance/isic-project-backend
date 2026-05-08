import json
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.hardware_service import (
    claim_device_from_scan,
    get_or_create_hardware_device,
    parse_hardware_topic,
    record_device_attendance,
    store_config_payload,
    store_health_payload,
    store_metrics_payload,
    store_status_payload,
)
from src.services.attendance_service import try_auto_record
from src.services.scan_service import create_scan, get_or_create_isic


async def handle_mqtt_message(
    session: AsyncSession,
    topic: str,
    payload: bytes,
) -> None:
    try:
        message_str = payload.decode("utf-8")
    except UnicodeDecodeError:
        logger.error("Invalid UTF-8 encoding in payload on topic {}", topic)
        return

    parsed_topic = parse_hardware_topic(topic)
    if parsed_topic is None:
        logger.warning("Unexpected MQTT topic structure: {}", topic)
        return

    device = await get_or_create_hardware_device(
        session,
        base_topic=parsed_topic.base_topic,
        device_id=parsed_topic.device_id,
    )

    try:
        if parsed_topic.kind == "attendance":
            await _handle_attendance_batch(
                session, device, topic, message_str
            )
        elif parsed_topic.kind == "health":
            _handle_health(device, message_str)
            await session.commit()
        elif parsed_topic.kind == "status":
            _handle_status(device, message_str)
            await session.commit()
        elif parsed_topic.kind == "metrics":
            _handle_metrics(device, message_str)
            await session.commit()
        elif parsed_topic.kind == "config":
            _handle_config(device, parsed_topic.section, message_str)
            await session.commit()
        else:
            logger.warning(
                "Unknown topic suffix '{}' from device {}",
                parsed_topic.kind,
                parsed_topic.device_id,
            )
    except json.JSONDecodeError:
        logger.warning(
            "Invalid JSON payload on topic {} from device {}",
            topic,
            parsed_topic.device_id,
        )
    except ValueError as err:
        logger.warning(
            "Invalid payload shape on topic {} from device {}: {}",
            topic,
            parsed_topic.device_id,
            err,
        )
    except SQLAlchemyError:
        logger.exception(
            "Database error while handling MQTT message from device {}",
            parsed_topic.device_id,
        )


async def _handle_attendance_batch(
    session: AsyncSession,
    device: "HardwareDevice",  # type: ignore[name-defined]  # noqa: F821
    topic: str,
    message_str: str,
) -> None:
    data = json.loads(message_str)

    # Backward compat: single dict → wrap in list
    records: list[dict[str, Any]]
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = [data]
    else:
        logger.warning(
            "Unexpected payload type from device {}: {}",
            device.device_id,
            type(data),
        )
        return

    for record in records:
        if not isinstance(record, dict):
            logger.warning(
                "Skipping non-dict record from device {}", device.device_id
            )
            continue

        # uid (new) → isic_identifier / isic_id (legacy fallback)
        identifier = (
            record.get("uid")
            or record.get("isic_identifier")
            or record.get("isic_id")
        )
        if not identifier:
            logger.warning(
                "Skipping record without uid from device {}", device.device_id
            )
            continue

        ts_ms = record.get("ts", 0)
        seq = record.get("seq")

        timestamp: datetime | None = None
        if isinstance(ts_ms, (int, float)) and ts_ms > 0:
            timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            logger.info(
                "SCAN ts_ms={} → utc={}", ts_ms, timestamp.strftime("%Y-%m-%d %H:%M:%S %Z")
            )
        else:
            logger.info("SCAN no ts from device, will use server time")

        isic = await get_or_create_isic(
            session=session,
            isic_identifier=str(identifier),
        )
        scan = await create_scan(
            session=session,
            isic_id=isic.id,
            timestamp=timestamp,
            hardware_device_id=device.id,
            mqtt_topic=topic,
            mqtt_sequence=seq if isinstance(seq, int) else None,
        )
        record_device_attendance(device, scan.timestamp)
        logger.info(
            "Created scan for '{}' from device {} (seq={})",
            identifier,
            device.device_id,
            seq,
        )

        updated = await try_auto_record(
            session=session,
            isic_id=isic.id,
            scan_id=scan.id,
            scan_timestamp=scan.timestamp,
        )
        claimed_teacher = await claim_device_from_scan(
            session=session,
            device=device,
            scanned_identifier=str(identifier),
            scanned_at=scan.timestamp,
        )
        if claimed_teacher is not None:
            logger.info(
                "Auto-claimed device {} for teacher {} via scan",
                device.device_id,
                claimed_teacher.id,
            )
        if updated:
            await session.commit()
            logger.info(
                "Auto-recorded attendance for {} lessons (device {})",
                len(updated),
                device.device_id,
            )
        else:
            await session.commit()


def _handle_health(
    device: "HardwareDevice",  # type: ignore[name-defined]  # noqa: F821
    message_str: str,
) -> None:
    store_health_payload(device, message_str)
    logger.info(
        "Health snapshot from device {}: {}",
        device.device_id,
        device.health_payload,
    )


def _handle_status(
    device: "HardwareDevice",  # type: ignore[name-defined]  # noqa: F821
    message_str: str,
) -> None:
    store_status_payload(device, message_str)
    logger.info("Status heartbeat from device {}", device.device_id)


def _handle_metrics(
    device: "HardwareDevice",  # type: ignore[name-defined]  # noqa: F821
    message_str: str,
) -> None:
    store_metrics_payload(device, message_str)
    logger.info(
        "Metrics snapshot from device {}: {}",
        device.device_id,
        device.metrics_payload,
    )


def _handle_config(
    device: "HardwareDevice",  # type: ignore[name-defined]  # noqa: F821
    section: str | None,
    message_str: str,
) -> None:
    store_config_payload(device, message_str, section)
    logger.info(
        "Config snapshot from device {} (section={}): {}",
        device.device_id,
        section or "full",
        device.config_payload,
    )
