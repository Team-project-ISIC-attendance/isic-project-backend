"""FastAPI routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_db
from src.models.scan import ISICScan
from src.services.scan_service import get_scan_by_id, get_scans

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/scans", response_model=list[dict[str, str | int]])
async def list_scans(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str | int]]:
    """Get list of ISIC scans."""
    scans = await get_scans(db, limit=limit, offset=offset)
    return [_scan_to_dict(scan) for scan in scans]


@router.get("/scans/{scan_id}", response_model=dict[str, str | int] | None)
async def get_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int] | None:
    """Get a specific ISIC scan by ID."""
    scan = await get_scan_by_id(db, scan_id)
    if scan is None:
        return None
    return _scan_to_dict(scan)


def _scan_to_dict(scan: ISICScan) -> dict[str, str | int]:
    """Convert ISICScan model to dictionary."""
    return {
        "id": scan.id,
        "isic_identifier": scan.isic_identifier,
        "timestamp": scan.timestamp.isoformat(),
        "created_at": scan.created_at.isoformat(),
    }

