from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.isic import ISIC
from src.models.scan import ISICScan


def normalize_isic_identifier(isic_identifier: str) -> str:
    return isic_identifier.strip().upper()


async def get_or_create_isic(
    session: AsyncSession,
    isic_identifier: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> ISIC:
    normalized_identifier = normalize_isic_identifier(isic_identifier)
    stmt = select(ISIC).where(
        func.upper(func.trim(ISIC.isic_identifier)) == normalized_identifier
    )
    result = await session.execute(stmt)
    isic = result.scalar_one_or_none()

    if isic is None:
        isic = ISIC(
            isic_identifier=normalized_identifier,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(isic)
        await session.flush()
    elif isic.isic_identifier != normalized_identifier:
        isic.isic_identifier = normalized_identifier

    return isic


def _get_current_timestamp_if_none(timestamp: datetime | None) -> datetime:
    if timestamp is None:
        return datetime.now(UTC)
    return timestamp


async def create_scan(
    session: AsyncSession,
    isic_id: int,
    timestamp: datetime | None = None,
) -> ISICScan:
    scan_timestamp = _get_current_timestamp_if_none(timestamp)

    scan = ISICScan(
        isic_id=isic_id,
        timestamp=scan_timestamp,
    )
    session.add(scan)
    await session.commit()
    await session.refresh(scan)
    return scan


async def create_scan_with_identifier(
    session: AsyncSession,
    isic_identifier: str,
    first_name: str | None = None,
    last_name: str | None = None,
    timestamp: datetime | None = None,
) -> ISICScan:
    isic = await get_or_create_isic(
        session, isic_identifier, first_name, last_name
    )
    return await create_scan(session, isic.id, timestamp)


async def get_scans(
    session: AsyncSession,
    limit: int,
    offset: int,
) -> list[ISICScan]:
    stmt = (
        select(ISICScan)
        .options(selectinload(ISICScan.isic))
        .order_by(ISICScan.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_scan_by_id(
    session: AsyncSession,
    scan_id: int,
) -> ISICScan | None:
    stmt = (
        select(ISICScan)
        .options(selectinload(ISICScan.isic))
        .where(ISICScan.id == scan_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_isic_by_identifier(
    session: AsyncSession,
    isic_identifier: str,
) -> ISIC | None:
    normalized_identifier = normalize_isic_identifier(isic_identifier)
    stmt = select(ISIC).where(
        func.upper(func.trim(ISIC.isic_identifier)) == normalized_identifier
    )
    result = await session.execute(stmt)
    isic = result.scalar_one_or_none()
    if isic is not None and isic.isic_identifier != normalized_identifier:
        isic.isic_identifier = normalized_identifier
    return isic


async def update_isic(
    session: AsyncSession,
    isic_identifier: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> ISIC | None:
    isic = await get_isic_by_identifier(session, isic_identifier)
    if isic is None:
        return None

    if first_name is not None:
        isic.first_name = first_name
    if last_name is not None:
        isic.last_name = last_name

    await session.commit()
    await session.refresh(isic)
    return isic
