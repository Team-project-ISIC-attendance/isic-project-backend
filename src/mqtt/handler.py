import json
from datetime import datetime
from typing import Any, cast

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.scan_service import create_scan_with_identifier


def _decode_payload_to_string(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        logger.error("Invalid UTF-8 encoding in payload")
        raise


def _normalize_utc_timestamp(timestamp_str: str) -> str:
    return timestamp_str.replace("Z", "+00:00")


def _parse_iso_timestamp(timestamp_str: str) -> datetime | None:
    try:
        normalized = _normalize_utc_timestamp(timestamp_str)
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        logger.warning("Invalid timestamp format, using current time")
        return None


def _try_parse_json(message_str: str) -> dict[str, Any] | None:
    try:
        result = json.loads(message_str)
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
        return None
    except json.JSONDecodeError:
        return None


def _extract_identifier_from_json(message_data: dict[str, Any]) -> str | None:
    return message_data.get("isic_identifier") or message_data.get("isic_id")


def _extract_timestamp_from_json(message_data: dict[str, Any]) -> datetime | None:
    timestamp_str = message_data.get("timestamp")
    if timestamp_str:
        return _parse_iso_timestamp(timestamp_str)
    return None


def _extract_from_json(
    message_data: dict[str, Any]
) -> tuple[str | None, datetime | None]:
    isic_identifier = _extract_identifier_from_json(message_data)
    timestamp = _extract_timestamp_from_json(message_data)
    return isic_identifier, timestamp


def _extract_identifier_from_plain_text(message_str: str) -> str | None:
    stripped = message_str.strip()
    return stripped if stripped else None


def _extract_from_plain_text(
    message_str: str
) -> tuple[str | None, None]:
    isic_identifier = _extract_identifier_from_plain_text(message_str)
    return isic_identifier, None


def _parse_message(
    message_str: str
) -> tuple[str | None, datetime | None]:
    message_data = _try_parse_json(message_str)
    if message_data:
        return _extract_from_json(message_data)
    return _extract_from_plain_text(message_str)


async def _create_scan_record(
    session: AsyncSession,
    isic_identifier: str,
    timestamp: datetime | None,
) -> None:
    await create_scan_with_identifier(
        session=session,
        isic_identifier=isic_identifier,
        timestamp=timestamp,
    )


async def handle_mqtt_message(
    session: AsyncSession,
    topic: str,
    payload: bytes,
) -> None:
    try:
        message_str = _decode_payload_to_string(payload)
        logger.info("Received MQTT message on topic: {}", topic)

        isic_identifier, timestamp = _parse_message(message_str)
        if not isic_identifier:
            logger.warning("Invalid message format: missing ISIC identifier")
            return

        await _create_scan_record(session, isic_identifier, timestamp)
        logger.info("Created scan record for ISIC identifier")

    except UnicodeDecodeError:
        logger.error("Failed to decode MQTT payload")
    except SQLAlchemyError:
        logger.exception("Database error while handling MQTT message")

