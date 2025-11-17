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

router = APIRouter()


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
        isic_identifier=updated_isic.isic_identifier,
        first_name=updated_isic.first_name,
        last_name=updated_isic.last_name,
        created_at=updated_isic.created_at.isoformat(),
    )


def _scan_to_response(scan: ISICScan) -> ScanResponse:
    return ScanResponse(
        id=scan.id,
        isic_id=scan.isic_id,
        isic_identifier=scan.isic.isic_identifier,
        first_name=scan.isic.first_name,
        last_name=scan.isic.last_name,
        timestamp=scan.timestamp.isoformat(),
        created_at=scan.created_at.isoformat(),
    )

