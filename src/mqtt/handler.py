import json
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.attendance_service import try_auto_record
from src.services.scan_service import create_scan_with_identifier


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

    topic_parts = topic.split("/")
    if len(topic_parts) < 3:
        logger.warning("Unexpected MQTT topic structure: {}", topic)
        return

    device_id = topic_parts[-2]
    suffix = topic_parts[-1]

    try:
        if suffix == "attendance":
            await _handle_attendance_batch(session, device_id, message_str)
        elif suffix == "health":
            _handle_health(device_id, message_str)
        elif suffix == "metrics":
            _handle_metrics(device_id, message_str)
        else:
            logger.warning(
                "Unknown topic suffix '{}' from device {}", suffix, device_id
            )
    except json.JSONDecodeError:
        logger.warning(
            "Invalid JSON payload on topic {} from device {}", topic, device_id
        )
    except SQLAlchemyError:
        logger.exception(
            "Database error while handling MQTT message from device {}",
            device_id,
        )


async def _handle_attendance_batch(
    session: AsyncSession,
    device_id: str,
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
            "Unexpected payload type from device {}: {}", device_id, type(data)
        )
        return

    for record in records:
        if not isinstance(record, dict):
            logger.warning("Skipping non-dict record from device {}", device_id)
            continue

        # uid (new) → isic_identifier / isic_id (legacy fallback)
        identifier = (
            record.get("uid")
            or record.get("isic_identifier")
            or record.get("isic_id")
        )
        if not identifier:
            logger.warning(
                "Skipping record without uid from device {}", device_id
            )
            continue

        ts_ms = record.get("ts", 0)
        seq = record.get("seq")

        timestamp: datetime | None = None
        if isinstance(ts_ms, (int, float)) and ts_ms > 0:
            timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)

        scan = await create_scan_with_identifier(
            session=session,
            isic_identifier=str(identifier),
            timestamp=timestamp,
        )
        logger.info(
            "Created scan for '{}' from device {} (seq={})",
            identifier,
            device_id,
            seq,
        )

        updated = await try_auto_record(
            session=session,
            isic_id=scan.isic_id,
            scan_id=scan.id,
            scan_timestamp=scan.timestamp,
        )
        if updated:
            logger.info(
                "Auto-recorded attendance for {} lessons (device {})",
                len(updated),
                device_id,
            )


def _handle_health(device_id: str, message_str: str) -> None:
    data = json.loads(message_str)
    logger.info("Health snapshot from device {}: {}", device_id, data)


def _handle_metrics(device_id: str, message_str: str) -> None:
    data = json.loads(message_str)
    logger.info("Metrics snapshot from device {}: {}", device_id, data)
