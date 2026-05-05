import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.models.hardware_device import HardwareDevice
from src.models.user import UserRole
from src.mqtt.client import MQTTClient
from tests.helpers.mqtt_simulator import (
    publish_attendance_message,
    publish_config_message,
    publish_health_message,
    publish_metrics_message,
    wait_for_message_processing,
)
from tests.test_auth import create_test_user, get_auth_header


@pytest.mark.asyncio
async def test_hardware_snapshots_and_scan_source_visible_via_api(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await create_test_user(
        db_session, "admin@hardware1.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@hardware1.sk", "pass")

    device_id = "HW-ROOM-01"
    base_topic = "campus/isic"
    app.state.mqtt_client = mqtt_client

    await publish_health_message(
        mqtt_host,
        mqtt_port,
        base_topic=base_topic,
        device_id=device_id,
        data={
            "device_id": "WRONG-PAYLOAD-ID",
            "firmware": "1.0.3",
            "state": "healthy",
            "uptime_s": 1234,
            "free_heap": 32768,
        },
    )
    await publish_metrics_message(
        mqtt_host,
        mqtt_port,
        base_topic=base_topic,
        device_id=device_id,
        data={
            "MqttService": {
                "state": "running",
                "published": 25,
                "failed": 0,
            },
            "AttendanceService": {
                "state": "running",
                "cards_processed": 12,
            },
        },
    )
    await publish_config_message(
        mqtt_host,
        mqtt_port,
        {"locationId": "LAB-A1", "deviceId": "NEW-ID-IGNORED"},
        base_topic=base_topic,
        device_id=device_id,
        section="device",
    )
    await publish_config_message(
        mqtt_host,
        mqtt_port,
        {"baseTopic": "other/topic", "port": 1883},
        base_topic=base_topic,
        device_id=device_id,
        section="mqtt",
    )
    await publish_attendance_message(
        mqtt_host,
        mqtt_port,
        uid="HW_API_SCAN_01",
        base_topic=base_topic,
        device_id=device_id,
        seq=7,
    )
    await wait_for_message_processing()

    device_response = await test_client.get(
        f"/hardware/devices/{device_id}",
        headers=headers,
    )
    assert device_response.status_code == 200
    device_body = device_response.json()
    assert device_body["device_id"] == device_id
    assert device_body["base_topic"] == base_topic
    assert device_body["location_id"] == "LAB-A1"
    assert device_body["firmware"] == "1.0.3"
    assert device_body["health_state"] == "healthy"
    assert device_body["health_payload"]["device_id"] == "WRONG-PAYLOAD-ID"
    assert device_body["metrics_payload"]["MqttService"]["published"] == 25
    assert device_body["config_payload"]["device"]["locationId"] == "LAB-A1"
    assert device_body["config_payload"]["mqtt"]["baseTopic"] == "other/topic"
    assert device_body["last_seen_at"] is not None
    assert device_body["last_health_at"] is not None
    assert device_body["last_metrics_at"] is not None
    assert device_body["last_config_at"] is not None
    assert device_body["last_attendance_at"] is not None

    scans_response = await test_client.get("/scans?limit=20&offset=0")
    assert scans_response.status_code == 200
    scan_body = next(
        scan
        for scan in scans_response.json()
        if scan["isic_identifier"] == "HW_API_SCAN_01"
    )
    assert scan_body["hardware_device_identifier"] == device_id
    assert scan_body["mqtt_topic"] == f"{base_topic}/{device_id}/attendance"
    assert scan_body["mqtt_sequence"] == 7


@pytest.mark.asyncio
async def test_hardware_control_routes_publish_documented_topics(
    mqtt_client: MQTTClient,
    test_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await create_test_user(
        db_session, "admin@hardware2.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@hardware2.sk", "pass")

    device = HardwareDevice(device_id="HW-CMD-01", base_topic="campus/isic")
    db_session.add(device)
    await db_session.commit()

    published_messages: list[tuple[str, object]] = []

    async def fake_publish(
        topic: str,
        payload: bytes | bytearray | str | object = b"",
        *,
        retain: bool = False,
    ) -> None:
        published_messages.append((topic, payload))

    async def fake_publish_json(
        topic: str,
        payload: object,
        *,
        retain: bool = False,
    ) -> None:
        published_messages.append((topic, payload))

    monkeypatch.setattr(mqtt_client, "publish", fake_publish)
    monkeypatch.setattr(mqtt_client, "publish_json", fake_publish_json)
    app.state.mqtt_client = mqtt_client

    health_resp = await test_client.post(
        "/hardware/devices/HW-CMD-01/health/request",
        headers=headers,
    )
    assert health_resp.status_code == 202
    assert health_resp.json()["topic"] == "campus/isic/HW-CMD-01/health/request"

    metrics_resp = await test_client.post(
        "/hardware/devices/HW-CMD-01/metrics/request",
        headers=headers,
    )
    assert metrics_resp.status_code == 202
    assert metrics_resp.json()["topic"] == "campus/isic/HW-CMD-01/metrics/request"

    config_get_resp = await test_client.post(
        "/hardware/devices/HW-CMD-01/config/request?section=mqtt",
        headers=headers,
    )
    assert config_get_resp.status_code == 202
    assert config_get_resp.json()["topic"] == "campus/isic/HW-CMD-01/config/get/mqtt"

    config_put_resp = await test_client.put(
        "/hardware/devices/HW-CMD-01/config",
        json={"wifi": {"stationSsid": "ssid"}},
        headers=headers,
    )
    assert config_put_resp.status_code == 202
    assert config_put_resp.json()["topic"] == "campus/isic/HW-CMD-01/config/set"

    config_section_put_resp = await test_client.put(
        "/hardware/devices/HW-CMD-01/config/attendance",
        json={"debounceIntervalMs": 800},
        headers=headers,
    )
    assert config_section_put_resp.status_code == 202
    assert (
        config_section_put_resp.json()["topic"]
        == "campus/isic/HW-CMD-01/config/set/attendance"
    )

    assert published_messages == [
        ("campus/isic/HW-CMD-01/health/request", b""),
        ("campus/isic/HW-CMD-01/metrics/request", b""),
        ("campus/isic/HW-CMD-01/config/get/mqtt", b""),
        ("campus/isic/HW-CMD-01/config/set", {"wifi": {"stationSsid": "ssid"}}),
        (
            "campus/isic/HW-CMD-01/config/set/attendance",
            {"debounceIntervalMs": 800},
        ),
    ]


@pytest.mark.asyncio
async def test_teacher_can_claim_multiple_devices_via_pairing_scan_flow(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    teacher = await create_test_user(
        db_session,
        "teacher@hardware-flow.sk",
        "pass",
        role=UserRole.teacher,
        first_name="Pair",
        last_name="Teacher",
    )
    headers = await get_auth_header(
        test_client, "teacher@hardware-flow.sk", "pass"
    )

    base_topic = "prod/readers"
    first_device_id = "HW-PAIR-01"
    second_device_id = "HW-PAIR-02"
    teacher_isic = "teacher-card-123"
    app.state.mqtt_client = mqtt_client

    for device_id in (first_device_id, second_device_id):
        await publish_health_message(
            mqtt_host,
            mqtt_port,
            base_topic=base_topic,
            device_id=device_id,
            data={"firmware": "2.1.0", "state": "healthy"},
        )
    await wait_for_message_processing()

    update_isic_response = await test_client.patch(
        "/auth/me/isic",
        json={"isic_identifier": teacher_isic},
        headers=headers,
    )
    assert update_isic_response.status_code == 200
    assert update_isic_response.json()["isic_identifier"] == "TEACHER-CARD-123"

    unclaimed_response = await test_client.get(
        "/hardware/devices/unclaimed",
        headers=headers,
    )
    assert unclaimed_response.status_code == 200
    assert {device["device_id"] for device in unclaimed_response.json()} == {
        first_device_id,
        second_device_id,
    }

    for device_id in (first_device_id, second_device_id):
        pairing_response = await test_client.post(
            f"/hardware/devices/{device_id}/pairing/start",
            headers=headers,
        )
        assert pairing_response.status_code == 201
        assert pairing_response.json()["status"] == "pending"

        await publish_attendance_message(
            mqtt_host,
            mqtt_port,
            uid=teacher_isic,
            base_topic=base_topic,
            device_id=device_id,
        )
        await wait_for_message_processing()

        pairing_status_response = await test_client.get(
            f"/hardware/devices/{device_id}/pairing",
            headers=headers,
        )
        assert pairing_status_response.status_code == 200
        assert pairing_status_response.json()["status"] == "completed"

    my_devices_response = await test_client.get(
        "/hardware/devices",
        headers=headers,
    )
    assert my_devices_response.status_code == 200
    my_devices = my_devices_response.json()
    assert {device["device_id"] for device in my_devices} == {
        first_device_id,
        second_device_id,
    }
    assert all(device["teacher_id"] == teacher.id for device in my_devices)
    assert all(device["is_claimed"] is True for device in my_devices)

    release_response = await test_client.delete(
        f"/hardware/devices/{first_device_id}/claim",
        headers=headers,
    )
    assert release_response.status_code == 200
    assert release_response.json()["teacher_id"] is None
    assert release_response.json()["is_claimed"] is False

    remaining_devices_response = await test_client.get(
        "/hardware/devices",
        headers=headers,
    )
    assert remaining_devices_response.status_code == 200
    assert [device["device_id"] for device in remaining_devices_response.json()] == [
        second_device_id
    ]

    returned_unclaimed_response = await test_client.get(
        "/hardware/devices/unclaimed",
        headers=headers,
    )
    assert returned_unclaimed_response.status_code == 200
    returned_unclaimed_ids = {
        device["device_id"] for device in returned_unclaimed_response.json()
    }
    assert first_device_id in returned_unclaimed_ids
