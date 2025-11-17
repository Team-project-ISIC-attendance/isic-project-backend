"""Service for managing ISIC scans."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.scan import ISICScan


async def create_scan(
    session: AsyncSession,
    isic_identifier: str,
    timestamp: datetime | None = None,
) -> ISICScan:
    """Create a new ISIC scan record."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    scan = ISICScan(
        isic_identifier=isic_identifier,
        timestamp=timestamp,
    )
    session.add(scan)
    await session.commit()
    await session.refresh(scan)
    return scan


async def get_scans(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> list[ISICScan]:
    """Get ISIC scans with pagination."""
    stmt = select(ISICScan).order_by(ISICScan.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_scan_by_id(
    session: AsyncSession,
    scan_id: int,
) -> ISICScan | None:
    """Get ISIC scan by ID."""
    stmt = select(ISICScan).where(ISICScan.id == scan_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

