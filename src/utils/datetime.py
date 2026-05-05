from datetime import UTC, datetime


def coerce_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return coerce_utc_datetime(value).isoformat()
