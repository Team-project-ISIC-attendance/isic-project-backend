import asyncio
import json

from aiomqtt import Client

DEFAULT_DEVICE_ID = "ISIC-ESP8266-001"


async def publish_scan_message(
    hostname: str,
    port: int,
    isic_identifier: str,
    timestamp: str | None = None,
) -> None:
    """Publish a simulated NFC scan message using the OLD payload format.

    Publishes to the new topic ``device/{device_id}/attendance`` but keeps
    the legacy ``{"isic_identifier": "..."}`` JSON shape so that existing
    tests act as backward-compatibility tests automatically.
    """
    message: dict[str, str] = {"isic_identifier": isic_identifier}
    if timestamp is not None:
        message["timestamp"] = timestamp
    async with Client(
        hostname=hostname, port=port, identifier="test-simulator"
    ) as client:
        await client.publish(
            f"device/{DEFAULT_DEVICE_ID}/attendance",
            payload=json.dumps(message),
        )


async def publish_attendance_message(
    hostname: str,
    port: int,
    uid: str,
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    timestamp_ms: int = 0,
    seq: int = 1,
    records: list[dict[str, object]] | None = None,
) -> None:
    """Publish a simulated attendance message using the NEW array payload format.

    If *records* is provided, it is sent as-is.  Otherwise a single-record
    array is built from *uid*, *timestamp_ms*, and *seq*.
    """
    if records is not None:
        payload = records
    else:
        payload = [{"uid": uid, "ts": timestamp_ms, "seq": seq}]
    async with Client(
        hostname=hostname, port=port, identifier="test-simulator-new"
    ) as client:
        await client.publish(
            f"device/{device_id}/attendance",
            payload=json.dumps(payload),
        )


async def publish_health_message(
    hostname: str,
    port: int,
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    data: dict[str, object] | None = None,
) -> None:
    """Publish a simulated health message."""
    payload = data or {"uptime_ms": 123456, "free_heap": 32000}
    async with Client(
        hostname=hostname, port=port, identifier="test-simulator-health"
    ) as client:
        await client.publish(
            f"device/{device_id}/health",
            payload=json.dumps(payload),
        )


async def publish_metrics_message(
    hostname: str,
    port: int,
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    data: dict[str, object] | None = None,
) -> None:
    """Publish a simulated metrics message."""
    payload = data or {"scans_total": 42, "publishes_ok": 40}
    async with Client(
        hostname=hostname, port=port, identifier="test-simulator-metrics"
    ) as client:
        await client.publish(
            f"device/{device_id}/metrics",
            payload=json.dumps(payload),
        )


async def publish_raw_message(
    hostname: str,
    port: int,
    topic: str,
    payload: str | bytes,
) -> None:
    """Publish an arbitrary raw message (for testing invalid payloads)."""
    async with Client(
        hostname=hostname, port=port, identifier="test-simulator-raw"
    ) as client:
        await client.publish(topic, payload=payload)


async def wait_for_message_processing() -> None:
    """Wait for the MQTT handler to process a published message."""
    await asyncio.sleep(0.5)
