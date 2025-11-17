"""MQTT message handler."""

import json
from datetime import datetime

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.scan_service import create_scan


async def handle_mqtt_message(
    session: AsyncSession,
    topic: str,
    payload: bytes,
) -> None:
    """Handle incoming MQTT message."""
    try:
        message_str = _decode_payload(payload)
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


def _decode_payload(payload: bytes) -> str:
    """Decode MQTT payload to string."""
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        logger.error("Invalid UTF-8 encoding in payload")
        raise


def _parse_message(message_str: str) -> tuple[str | None, datetime | None]:
    """Parse message string and extract ISIC identifier and timestamp."""
    message_data = _try_parse_json(message_str)
    if message_data:
        return _extract_from_json(message_data)
    return _extract_from_plain_text(message_str)


def _try_parse_json(message_str: str) -> dict | None:
    """Try to parse message as JSON."""
    try:
        return json.loads(message_str)
    except json.JSONDecodeError:
        return None


def _extract_from_json(message_data: dict) -> tuple[str | None, datetime | None]:
    """Extract ISIC identifier and timestamp from JSON data."""
    isic_identifier = message_data.get("isic_identifier") or message_data.get("isic_id")
    timestamp_str = message_data.get("timestamp")
    timestamp = _parse_timestamp(timestamp_str) if timestamp_str else None
    return isic_identifier, timestamp


def _extract_from_plain_text(message_str: str) -> tuple[str | None, None]:
    """Extract ISIC identifier from plain text message."""
    isic_identifier = message_str.strip()
    return isic_identifier if isic_identifier else None, None


def _parse_timestamp(timestamp_str: str) -> datetime | None:
    """Parse timestamp string to datetime object."""
    try:
        normalized = timestamp_str.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        logger.warning("Invalid timestamp format, using current time")
        return None


async def _create_scan_record(
    session: AsyncSession,
    isic_identifier: str,
    timestamp: datetime | None,
) -> object:
    """Create scan record in database."""
    return await create_scan(
        session=session,
        isic_identifier=isic_identifier,
        timestamp=timestamp,
    )

