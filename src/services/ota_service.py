import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.ota_firmware import OtaFirmware


def _firmware_dir() -> Path:
    path = Path(settings.firmware_storage_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def firmware_file_path(filename: str) -> Path:
    return _firmware_dir() / filename


async def create_firmware(
    db: AsyncSession,
    version: str,
    board: str,
    data: bytes,
    uploaded_by_id: int | None = None,
) -> OtaFirmware:
    md5 = hashlib.md5(data).hexdigest()
    filename = f"{board}_{version}_{md5[:8]}.bin"
    firmware_file_path(filename).write_bytes(data)

    firmware = OtaFirmware(
        version=version,
        board=board,
        filename=filename,
        md5=md5,
        size_bytes=len(data),
        uploaded_by_id=uploaded_by_id,
    )
    db.add(firmware)
    await db.commit()
    await db.refresh(firmware)
    return firmware


async def list_firmwares(db: AsyncSession) -> list[OtaFirmware]:
    result = await db.execute(
        select(OtaFirmware).order_by(OtaFirmware.uploaded_at.desc())
    )
    return list(result.scalars().all())


async def get_firmware(db: AsyncSession, firmware_id: int) -> OtaFirmware | None:
    return await db.get(OtaFirmware, firmware_id)


async def delete_firmware(db: AsyncSession, firmware: OtaFirmware) -> None:
    path = firmware_file_path(firmware.filename)
    if path.exists():
        path.unlink()
    await db.delete(firmware)
    await db.commit()


def build_firmware_server_url(firmware_id: int, base_url: str | None = None) -> str:
    if base_url:
        base = base_url.rstrip("/")
    elif settings.server_host:
        base = f"http://{settings.server_host}:{settings.http_port}"
    elif settings.http_host not in {"0.0.0.0", ""}:
        base = f"http://{settings.http_host}:{settings.http_port}"
    else:
        base = f"http://localhost:{settings.http_port}"
    return f"{base}/hardware/ota/firmware/{firmware_id}"
