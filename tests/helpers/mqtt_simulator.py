import asyncio
import json

from aiomqtt import Client


async def publish_scan_message(
    hostname: str,
    port: int,
    isic_identifier: str,
    timestamp: str | None = None,
) -> None:
    """Publish a simulated NFC scan message to the MQTT broker.

    Replicates the JSON payload the ESP8266 firmware sends when a student
    taps their ISIC card on the NFC reader.
    """
    message: dict[str, str] = {"isic_identifier": isic_identifier}
    if timestamp is not None:
        message["timestamp"] = timestamp
    async with Client(
        hostname=hostname, port=port, identifier="test-simulator"
    ) as client:
        await client.publish("isic/scan", payload=json.dumps(message))


async def wait_for_message_processing() -> None:
    """Wait for the MQTT handler to process a published message."""
    await asyncio.sleep(0.5)
