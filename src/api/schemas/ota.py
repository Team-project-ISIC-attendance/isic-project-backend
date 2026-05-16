from pydantic import BaseModel


class OtaFirmwareResponse(BaseModel):
    id: int
    version: str
    board: str
    filename: str
    md5: str
    size_bytes: int
    uploaded_at: str
    uploaded_by_id: int | None


class OtaDeployResponse(BaseModel):
    detail: str
    firmware_id: int
    device_id: str
    server_url: str


class OtaStatusResponse(BaseModel):
    state: str  # "completed" | "error" | "progress"
    payload: str
    timestamp: str
    progress: int | None = None  # 0-100, set when state == "progress"
