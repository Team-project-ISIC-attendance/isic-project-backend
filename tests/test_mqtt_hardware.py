"""Tests for the rewritten MQTT handler with new hardware payload format."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from src.mqtt.client import MQTTClient
from src.services.scan_service import get_scans
from tests.helpers.mqtt_simulator import (
    publish_attendance_message,
    publish_health_message,
    publish_metrics_message,
    publish_raw_message,
    publish_scan_message,
    wait_for_message_processing,
)
from tests.test_auth import create_test_user, get_auth_header
from tests.test_scan_attendance import _create_lesson_matching_now


@pytest.mark.asyncio
async def test_single_record_new_format(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """New array format with a single record creates ISICScan + ISIC."""
    await publish_attendance_message(
        mqtt_host,
        mqtt_port,
        uid="04A1B2C3D4",
        timestamp_ms=1710000000000,
        seq=1,
    )
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    matching = [s for s in scans if s.isic.isic_identifier == "04A1B2C3D4"]
    assert len(matching) == 1
    # ts=1710000000000 → 2024-03-09T16:00:00 UTC
    assert matching[0].timestamp.year == 2024
    assert matching[0].timestamp.month == 3
    assert matching[0].timestamp.day == 9


@pytest.mark.asyncio
async def test_batch_multiple_records(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Batch with 2 records creates 2 ISICScan records."""
    await publish_attendance_message(
        mqtt_host,
        mqtt_port,
        uid="BATCH_A",
        records=[
            {"uid": "BATCH_A", "ts": 0, "seq": 1},
            {"uid": "BATCH_B", "ts": 0, "seq": 2},
        ],
    )
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    ids_found = {s.isic.isic_identifier for s in scans}
    assert "BATCH_A" in ids_found
    assert "BATCH_B" in ids_found


@pytest.mark.asyncio
async def test_zero_timestamp_uses_server_time(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """ts=0 falls back to server time (approximately now)."""
    before = datetime.now(UTC)
    await publish_attendance_message(
        mqtt_host, mqtt_port, uid="ZERO_TS_01", timestamp_ms=0, seq=1
    )
    await wait_for_message_processing()
    after = datetime.now(UTC)

    scans = await get_scans(db_session, limit=100, offset=0)
    matching = [s for s in scans if s.isic.isic_identifier == "ZERO_TS_01"]
    assert len(matching) == 1
    scan_ts = matching[0].timestamp.replace(tzinfo=UTC)
    assert before - timedelta(seconds=5) <= scan_ts <= after + timedelta(seconds=5)


@pytest.mark.asyncio
async def test_backward_compat_old_format(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Old dict format {"isic_identifier":"..."} still works."""
    await publish_scan_message(mqtt_host, mqtt_port, "COMPAT01")
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    found = any(s.isic.isic_identifier == "COMPAT01" for s in scans)
    assert found


@pytest.mark.asyncio
async def test_backward_compat_single_object_with_uid(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Single object (not array) with uid field still works."""
    await publish_raw_message(
        mqtt_host,
        mqtt_port,
        "device/ISIC-ESP8266-001/attendance",
        '{"uid":"SINGLE01","ts":0,"seq":1}',
    )
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    found = any(s.isic.isic_identifier == "SINGLE01" for s in scans)
    assert found


@pytest.mark.asyncio
async def test_invalid_json_no_crash(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Invalid JSON payload doesn't crash the handler."""
    await publish_raw_message(
        mqtt_host,
        mqtt_port,
        "device/ISIC-ESP8266-001/attendance",
        "not-json",
    )
    await wait_for_message_processing()
    # No crash = success; verify no scan created
    scans = await get_scans(db_session, limit=100, offset=0)
    assert not any(s.isic.isic_identifier == "not-json" for s in scans)


@pytest.mark.asyncio
async def test_empty_payload_no_crash(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Empty payload doesn't crash the handler."""
    await publish_raw_message(
        mqtt_host,
        mqtt_port,
        "device/ISIC-ESP8266-001/attendance",
        "",
    )
    await wait_for_message_processing()
    # No crash = success


@pytest.mark.asyncio
async def test_missing_uid_skipped(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Record without uid is skipped."""
    await publish_attendance_message(
        mqtt_host,
        mqtt_port,
        uid="PLACEHOLDER",
        records=[{"ts": 123, "seq": 1}],
    )
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    # No scan created (record had no uid)
    assert not any(s.isic.isic_identifier == "PLACEHOLDER" for s in scans)


@pytest.mark.asyncio
async def test_mixed_valid_invalid_records(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Mixed batch: valid record processed, invalid skipped."""
    await publish_attendance_message(
        mqtt_host,
        mqtt_port,
        uid="PLACEHOLDER",
        records=[
            {"uid": "GOOD01", "ts": 0, "seq": 1},
            {"ts": 0, "seq": 2},  # missing uid
        ],
    )
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    assert any(s.isic.isic_identifier == "GOOD01" for s in scans)


@pytest.mark.asyncio
async def test_health_message_no_crash(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Health message is logged without crash, no scan created."""
    await publish_health_message(mqtt_host, mqtt_port)
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    assert not any(s.isic.isic_identifier == "uptime_ms" for s in scans)


@pytest.mark.asyncio
async def test_metrics_message_no_crash(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    db_session: AsyncSession,
) -> None:
    """Metrics message is logged without crash, no scan created."""
    await publish_metrics_message(mqtt_host, mqtt_port)
    await wait_for_message_processing()

    scans = await get_scans(db_session, limit=100, offset=0)
    assert not any(s.isic.isic_identifier == "scans_total" for s in scans)


@pytest.mark.asyncio
async def test_attendance_auto_record_new_format(
    mqtt_client: MQTTClient,
    mqtt_host: str,
    mqtt_port: int,
    test_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """New format attendance triggers auto-record (pritomny/scan)."""
    await create_test_user(
        db_session, "admin@hw1.sk", "pass", role=UserRole.admin
    )
    headers = await get_auth_header(test_client, "admin@hw1.sk", "pass")
    ids = await _create_lesson_matching_now(
        test_client, headers, "HW01", "HW_SCAN_01"
    )

    await publish_attendance_message(
        mqtt_host, mqtt_port, uid="HW_SCAN_01", timestamp_ms=0, seq=1
    )
    await wait_for_message_processing()

    att_resp = await test_client.get(
        f"/lessons/{ids['lesson_id']}/attendance", headers=headers
    )
    assert att_resp.status_code == 200
    student = att_resp.json()["students"][0]
    assert student["status"] == "pritomny"
    assert student["marked_by"] == "scan"
