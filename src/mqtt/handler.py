import json
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


def _parse_message(message_str: str) -> str | None:
    message_data = _try_parse_json(message_str)
    if message_data:
        return _extract_identifier_from_json(message_data)
    logger.warning("Invalid message format: must be valid JSON")
    return None


async def _create_scan_record(
    session: AsyncSession,
    isic_identifier: str,
) -> None:
    await create_scan_with_identifier(
        session=session,
        isic_identifier=isic_identifier,
        timestamp=None,
    )


async def handle_mqtt_message(
    session: AsyncSession,
    topic: str,
    payload: bytes,
) -> None:
    try:
        message_str = _decode_payload_to_string(payload)
        logger.info("Received MQTT message on topic: {}", topic)

        isic_identifier = _parse_message(message_str)
        if not isic_identifier:
            logger.warning("Invalid message format: must be valid JSON with 'isic_identifier' field")
            return

        await _create_scan_record(session, isic_identifier)
        logger.info("Created scan record for ISIC identifier")

    except UnicodeDecodeError:
        logger.error("Failed to decode MQTT payload")
    except SQLAlchemyError:
        logger.exception("Database error while handling MQTT message")

