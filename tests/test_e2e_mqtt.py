import asyncio
import json
from datetime import UTC, datetime

import pytest
from aiomqtt import Client
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.scan import ISICScan
from src.mqtt.client import MQTTClient
from src.services.scan_service import get_scans


async def publish_message(
    hostname: str,
    port: int,
    topic: str,
    payload: str | bytes,
) -> None:
    async with Client(
        hostname=hostname, port=port, identifier="test-publisher"
    ) as client:
        await client.publish(topic, payload=payload)


async def wait_for_message_processing() -> None:
    await asyncio.sleep(0.5)


def find_scan_by_identifier(scans: list[ISICScan], isic_identifier: str) -> ISICScan | None:
    for scan in scans:
        if scan.isic.isic_identifier == isic_identifier:
            return scan
    return None


@pytest.mark.asyncio
async def test_mqtt_json_message_with_required_fields_stored_in_database(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    isic_identifier = "TEST123456"
    message = {
        "isic_identifier": isic_identifier,
    }
    await publish_message(
        mqtt_host, mqtt_port, "isic/scan", json.dumps(message)
    )

    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=10, offset=0)
    assert len(scans) >= 1

    test_scan = find_scan_by_identifier(scans, isic_identifier)

    assert test_scan is not None, "Scan not found in database"
    assert test_scan.isic.isic_identifier == isic_identifier
    assert test_scan.isic.first_name is None
    assert test_scan.isic.last_name is None
    assert test_scan.timestamp is not None


@pytest.mark.asyncio
async def test_mqtt_json_message_stored_in_database(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    isic_identifier = "JSON123456"
    timestamp = datetime.now(UTC).isoformat()
    message = {
        "isic_identifier": isic_identifier,
        "timestamp": timestamp,
    }
    await publish_message(
        mqtt_host, mqtt_port, "isic/scan", json.dumps(message)
    )

    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=10, offset=0)
    assert len(scans) >= 1

    test_scan = find_scan_by_identifier(scans, isic_identifier)

    assert test_scan is not None, "Scan not found in database"
    assert test_scan.isic.isic_identifier == isic_identifier
    assert test_scan.isic.first_name is None
    assert test_scan.isic.last_name is None
    assert test_scan.timestamp is not None


@pytest.mark.asyncio
async def test_multiple_mqtt_messages_stored_in_database(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    identifiers = ["MULTI001", "MULTI002", "MULTI003"]
    for identifier in identifiers:
        message = {
            "isic_identifier": identifier,
        }
        await publish_message(
            mqtt_host, mqtt_port, "isic/scan", json.dumps(message)
        )
        await asyncio.sleep(0.1)

    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    found_identifiers = {scan.isic.isic_identifier for scan in scans}

    for identifier in identifiers:
        assert identifier in found_identifiers, f"Scan for {identifier} not found"


@pytest.mark.asyncio
async def test_can_fetch_scans_after_mqtt_message(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    isic_identifier = "FETCH123456"
    message = {
        "isic_identifier": isic_identifier,
    }
    await publish_message(
        mqtt_host, mqtt_port, "isic/scan", json.dumps(message)
    )

    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=10, offset=0)

    assert len(scans) >= 1
    assert any(scan.isic.isic_identifier == isic_identifier for scan in scans)

    test_scan = next(
        (scan for scan in scans if scan.isic.isic_identifier == isic_identifier),
        None,
    )
    assert test_scan is not None
    assert test_scan.id is not None
    assert test_scan.isic_id is not None
    assert test_scan.created_at is not None


@pytest.mark.asyncio
async def test_link_isic_after_bulk_upload_via_mqtt(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
    test_client: AsyncClient,
) -> None:
    isic_identifier = "BULK001"
    
    message = {
        "isic_identifier": isic_identifier,
    }
    await publish_message(
        mqtt_host, mqtt_port, "isic/scan", json.dumps(message)
    )
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=10, offset=0)
    test_scan = find_scan_by_identifier(scans, isic_identifier)
    assert test_scan is not None, "Scan not found after MQTT message"
    assert test_scan.isic.isic_identifier == isic_identifier
    assert test_scan.isic.first_name is None
    assert test_scan.isic.last_name is None

    update_response = await test_client.patch(
        f"/isics/{isic_identifier}",
        json={"first_name": "Jane", "last_name": "Smith"},
    )
    assert update_response.status_code == 200
    updated_data = update_response.json()
    assert updated_data["isic_identifier"] == isic_identifier
    assert updated_data["first_name"] == "Jane"
    assert updated_data["last_name"] == "Smith"
    db_session.expire_all()
    scans_after_update = await get_scans(db_session, limit=10, offset=0)
    updated_scan = find_scan_by_identifier(scans_after_update, isic_identifier)
    assert updated_scan is not None, "Scan not found after update"
    assert updated_scan.isic.first_name == "Jane"
    assert updated_scan.isic.last_name == "Smith"
    assert updated_scan.isic.id == test_scan.isic.id


@pytest.mark.asyncio
async def test_link_isic_affects_all_scans_for_same_isic(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
    test_client: AsyncClient,
) -> None:
    isic_identifier = "BULK002"
    
    for _ in range(3):
        message = {
            "isic_identifier": isic_identifier,
        }
        await publish_message(
            mqtt_host, mqtt_port, "isic/scan", json.dumps(message)
        )
        await asyncio.sleep(0.1)
    
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    isic_scans = [scan for scan in scans if scan.isic.isic_identifier == isic_identifier]
    assert len(isic_scans) == 3, f"Expected 3 scans, got {len(isic_scans)}"
    for scan in isic_scans:
        assert scan.isic.first_name is None
        assert scan.isic.last_name is None
        assert scan.isic.id == isic_scans[0].isic.id

    update_response = await test_client.patch(
        f"/isics/{isic_identifier}",
        json={"first_name": "John", "last_name": "Doe"},
    )
    assert update_response.status_code == 200
    db_session.expire_all()
    updated_scans = await get_scans(db_session, limit=100, offset=0)
    updated_isic_scans = [
        scan for scan in updated_scans if scan.isic.isic_identifier == isic_identifier
    ]
    assert len(updated_isic_scans) == 3
    for scan in updated_isic_scans:
        assert scan.isic.first_name == "John"
        assert scan.isic.last_name == "Doe"
        assert scan.isic.id == updated_isic_scans[0].isic.id


@pytest.mark.asyncio
async def test_link_isic_after_bulk_upload_via_api_response(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
    test_client: AsyncClient,
) -> None:
    isic_identifier = "BULK003"
    
    message = {
        "isic_identifier": isic_identifier,
    }
    await publish_message(
        mqtt_host, mqtt_port, "isic/scan", json.dumps(message)
    )
    await wait_for_message_processing()

    scans_response = await test_client.get("/scans?limit=10&offset=0")
    assert scans_response.status_code == 200
    scans_data = scans_response.json()
    test_scan_data = next(
        (scan for scan in scans_data if scan["isic_identifier"] == isic_identifier),
        None,
    )
    assert test_scan_data is not None, "Scan not found in API response"
    assert test_scan_data["first_name"] is None
    assert test_scan_data["last_name"] is None
    scan_id = test_scan_data["id"]

    update_response = await test_client.patch(
        f"/isics/{isic_identifier}",
        json={"first_name": "Alice", "last_name": "Johnson"},
    )
    assert update_response.status_code == 200

    scan_response = await test_client.get(f"/scans/{scan_id}")
    assert scan_response.status_code == 200
    updated_scan_data = scan_response.json()
    assert updated_scan_data["isic_identifier"] == isic_identifier
    assert updated_scan_data["first_name"] == "Alice"
    assert updated_scan_data["last_name"] == "Johnson"
    assert updated_scan_data["id"] == scan_id


@pytest.mark.asyncio
async def test_link_nonexistent_isic_returns_404(
    test_client: AsyncClient,
) -> None:
    update_response = await test_client.patch(
        "/isics/NONEXISTENT123",
        json={"first_name": "Test", "last_name": "User"},
    )
    assert update_response.status_code == 404

