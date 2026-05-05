from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.logging_config import format_log_time
from src.models.hardware_device import HardwareDevice
from src.services.hardware_service import record_device_attendance
from src.utils.datetime import isoformat_utc


def test_isoformat_utc_adds_offset_for_naive_datetimes() -> None:
    value = datetime(2026, 5, 5, 15, 6, 16, 140000)
    assert isoformat_utc(value) == "2026-05-05T15:06:16.140000+00:00"


def test_record_device_attendance_coerces_naive_timestamps_to_utc() -> None:
    device = HardwareDevice(device_id="HW-TIME-01", base_topic="device")

    record_device_attendance(device, datetime(2026, 5, 5, 15, 6, 16))

    assert device.last_attendance_at == datetime(2026, 5, 5, 15, 6, 16, tzinfo=UTC)
    assert device.last_seen_at == datetime(2026, 5, 5, 15, 6, 16, tzinfo=UTC)


def test_log_time_uses_bratislava_offset() -> None:
    timestamp = datetime(2026, 5, 5, 15, 6, 16, 140000, tzinfo=UTC)

    assert (
        format_log_time(timestamp, ZoneInfo("Europe/Bratislava"))
        == "2026-05-05 17:06:16.140 +02:00"
    )
