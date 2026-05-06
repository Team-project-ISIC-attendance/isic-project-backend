from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Health status")


class ScanQueryParams(BaseModel):
    limit: int = Field(..., ge=1, le=100, description="Maximum number of scans to return")
    offset: int = Field(..., ge=0, description="Number of scans to skip")


class ScanResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "isic_id": 1,
                "isic_identifier": "ISIC123456",
                "first_name": None,
                "last_name": None,
                "hardware_device_id": 1,
                "hardware_device_identifier": "ISIC-ESP8266-001",
                "mqtt_topic": "device/ISIC-ESP8266-001/attendance",
                "mqtt_sequence": 42,
                "timestamp": "2024-01-01T12:00:00+00:00",
                "created_at": "2024-01-01T12:00:00+00:00",
            }
        }
    )

    id: int = Field(..., description="Scan ID")
    isic_id: int = Field(..., description="ISIC ID")
    isic_identifier: str = Field(..., description="ISIC identifier")
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")
    hardware_device_id: int | None = Field(None, description="Hardware device ID")
    hardware_device_identifier: str | None = Field(
        None, description="Hardware device identifier"
    )
    mqtt_topic: str | None = Field(None, description="MQTT topic used for the scan")
    mqtt_sequence: int | None = Field(
        None, description="Firmware sequence number attached to the scan"
    )
    timestamp: str = Field(..., description="Scan timestamp in ISO format")
    created_at: str = Field(..., description="Scan creation timestamp in ISO format")


class ISICUpdateRequest(BaseModel):
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")


class ISICResponse(BaseModel):
    id: int = Field(..., description="ISIC ID")
    student_identifier: str | None = Field(
        None, description="Student identifier used for UI display"
    )
    isic_identifier: str = Field(..., description="ISIC identifier")
    full_name: str | None = Field(None, description="Full student name")
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")
    study_identification: str | None = Field(
        None, description="Study identification"
    )
    email_is: str | None = Field(None, description="Institutional email")
    created_at: str = Field(..., description="ISIC creation timestamp in ISO format")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    isic_identifier: str | None = None
    first_name: str
    last_name: str
    role: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    isic_identifier: str | None = None
    first_name: str
    last_name: str
    role: str = "teacher"


class UserISICUpdateRequest(BaseModel):
    isic_identifier: str | None = Field(
        None, description="Teacher ISIC identifier used for hardware pairing"
    )


class UserUpdateRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    isic_identifier: str | None = None
