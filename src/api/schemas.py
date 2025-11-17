from typing import ClassVar

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Health status")


class ScanQueryParams(BaseModel):
    limit: int = Field(..., ge=1, le=100, description="Maximum number of scans to return")
    offset: int = Field(..., ge=0, description="Number of scans to skip")


class ScanResponse(BaseModel):
    id: int = Field(..., description="Scan ID")
    isic_id: int = Field(..., description="ISIC ID")
    isic_identifier: str = Field(..., description="ISIC identifier")
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")
    timestamp: str = Field(..., description="Scan timestamp in ISO format")
    created_at: str = Field(..., description="Scan creation timestamp in ISO format")

    class Config:
        json_schema_extra: ClassVar[dict[str, dict[str, int | str | None]]] = {
            "example": {
                "id": 1,
                "isic_id": 1,
                "isic_identifier": "ISIC123456",
                "first_name": None,
                "last_name": None,
                "timestamp": "2024-01-01T12:00:00+00:00",
                "created_at": "2024-01-01T12:00:00+00:00",
            }
        }


class ISICUpdateRequest(BaseModel):
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")


class ISICResponse(BaseModel):
    id: int = Field(..., description="ISIC ID")
    isic_identifier: str = Field(..., description="ISIC identifier")
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")
    created_at: str = Field(..., description="ISIC creation timestamp in ISO format")

