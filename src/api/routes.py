from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    HealthResponse,
    ISICResponse,
    ISICUpdateRequest,
    ScanResponse,
)
from src.database.connection import get_db
from src.models.scan import ISICScan
from src.services.scan_service import get_scan_by_id, get_scans, update_isic
from src.utils.datetime import isoformat_utc

router = APIRouter(tags=["scans"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/scans", response_model=list[ScanResponse])
async def list_scans(
    limit: int = Query(..., ge=1, le=100, description="Maximum number of scans to return"),
    offset: int = Query(..., ge=0, description="Number of scans to skip"),
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[ScanResponse]:
    scans = await get_scans(db, limit=limit, offset=offset)
    return [_scan_to_response(scan) for scan in scans]


@router.get("/scans/{scan_id}", response_model=ScanResponse | None)
async def get_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ScanResponse | None:
    scan = await get_scan_by_id(db, scan_id)
    if scan is None:
        return None
    return _scan_to_response(scan)


@router.patch("/isics/{isic_identifier}", response_model=ISICResponse)
async def update_isic_info(
    isic_identifier: str,
    update_data: ISICUpdateRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ISICResponse:
    updated_isic = await update_isic(
        db,
        isic_identifier,
        first_name=update_data.first_name,
        last_name=update_data.last_name,
    )
    if updated_isic is None:
        raise HTTPException(status_code=404, detail="ISIC not found")
    return ISICResponse(
        id=updated_isic.id,
        student_identifier=updated_isic.student_identifier,
        isic_identifier=updated_isic.isic_identifier,
        full_name=updated_isic.full_name,
        first_name=updated_isic.first_name,
        last_name=updated_isic.last_name,
        study_identification=updated_isic.study_identification,
        email_is=updated_isic.email_is,
        created_at=isoformat_utc(updated_isic.created_at) or "",
    )


def _scan_to_response(scan: ISICScan) -> ScanResponse:
    return ScanResponse(
        id=scan.id,
        isic_id=scan.isic_id,
        isic_identifier=scan.isic.isic_identifier,
        first_name=scan.isic.first_name,
        last_name=scan.isic.last_name,
        hardware_device_id=scan.hardware_device_id,
        hardware_device_identifier=(
            scan.hardware_device.device_id
            if scan.hardware_device is not None
            else None
        ),
        mqtt_topic=scan.mqtt_topic,
        mqtt_sequence=scan.mqtt_sequence,
        timestamp=isoformat_utc(scan.timestamp) or "",
        created_at=isoformat_utc(scan.created_at) or "",
    )
