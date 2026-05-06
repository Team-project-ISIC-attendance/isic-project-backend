from typing import Any

from pydantic import BaseModel, Field, RootModel


class HardwareDeviceSummaryResponse(BaseModel):
    id: int
    device_id: str
    base_topic: str
    teacher_id: int | None
    teacher_name: str | None
    claimed_at: str | None
    is_claimed: bool
    location_id: str | None
    firmware: str | None
    health_state: str | None
    is_online: bool
    connectivity_state: str
    last_seen_at: str | None
    last_attendance_at: str | None
    last_health_at: str | None
    last_metrics_at: str | None
    last_config_at: str | None


class HardwareDeviceDetailResponse(HardwareDeviceSummaryResponse):
    health_payload: dict[str, Any] | None
    metrics_payload: dict[str, Any] | None
    config_payload: dict[str, Any] | None


class HardwareSnapshotResponse(BaseModel):
    device_id: str
    received_at: str | None = Field(
        None, description="Timestamp when this snapshot was last stored"
    )
    payload: dict[str, Any] | None


class HardwareCommandResponse(BaseModel):
    detail: str
    topic: str


class PairingSessionResponse(BaseModel):
    device_id: str
    teacher_id: int
    teacher_isic_identifier: str
    status: str
    started_at: str
    expires_at: str
    completed_at: str | None


class ConfigRequestPayload(RootModel[dict[str, Any]]):
    pass
