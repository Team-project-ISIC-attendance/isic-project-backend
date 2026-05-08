import sys
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger

from src.config import settings


def _resolve_log_timezone() -> tzinfo:
    try:
        return ZoneInfo(settings.log_time_zone)
    except ZoneInfoNotFoundError:
        return UTC


def format_log_time(
    timestamp: datetime,
    timezone: tzinfo | None = None,
) -> str:
    localized = timestamp.astimezone(timezone or _resolve_log_timezone())
    offset = localized.strftime("%z")
    formatted_offset = f"{offset[:3]}:{offset[3:]}" if offset else "+00:00"
    return (
        f"{localized.strftime('%Y-%m-%d %H:%M:%S')}"
        f".{localized.microsecond // 1000:03d} {formatted_offset}"
    )


def _inject_local_log_time(record: dict) -> None:
    record["extra"]["local_time"] = format_log_time(record["time"])


def configure_logging() -> None:
    logger.remove()
    logger.configure(patcher=_inject_local_log_time)
    logger.add(
        sys.stderr,
        level="DEBUG" if settings.debug else "INFO",
        format=(
            "{extra[local_time]} | {level: <8} | "
            "{name}:{function}:{line} - {message}\n{exception}"
        ),
        backtrace=settings.debug,
        diagnose=settings.debug,
    )
