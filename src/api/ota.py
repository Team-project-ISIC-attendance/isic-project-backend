import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_mqtt_client
from src.api.schemas.ota import OtaDeployResponse, OtaFirmwareResponse, OtaStatusResponse
from src.mqtt.handler import clear_ota_state, get_ota_state
from src.database.connection import get_db
from src.models.user import User, UserRole
from src.mqtt.client import MQTTClient
from src.services.hardware_service import build_device_topic, get_hardware_device
from src.services.ota_service import (
    build_firmware_server_url,
    create_firmware,
    delete_firmware,
    firmware_file_path,
    get_firmware,
    list_firmwares,
)
from src.utils.datetime import isoformat_utc

router = APIRouter(prefix="/hardware/ota", tags=["ota"])

SUPPORTED_BOARDS = {"esp8266", "esp32"}


def _require_admin(user: User) -> None:
    if user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )


def _firmware_response(fw: "OtaFirmware") -> OtaFirmwareResponse:  # type: ignore[name-defined]  # noqa: F821
    return OtaFirmwareResponse(
        id=fw.id,
        version=fw.version,
        board=fw.board,
        filename=fw.filename,
        md5=fw.md5,
        size_bytes=fw.size_bytes,
        uploaded_at=isoformat_utc(fw.uploaded_at) or "",
        uploaded_by_id=fw.uploaded_by_id,
    )


@router.post(
    "/firmware",
    response_model=OtaFirmwareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a firmware binary",
)
async def upload_firmware(
    file: UploadFile,
    version: str,
    board: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> OtaFirmwareResponse:
    _require_admin(current_user)
    if board not in SUPPORTED_BOARDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported board '{board}'. Supported: {sorted(SUPPORTED_BOARDS)}",
        )
    if not version.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Version must not be empty",
        )
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    fw = await create_firmware(
        db, version=version.strip(), board=board, data=data, uploaded_by_id=current_user.id
    )
    return _firmware_response(fw)


@router.get(
    "/firmware",
    response_model=list[OtaFirmwareResponse],
    summary="List all uploaded firmware builds",
)
async def list_firmware_builds(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[OtaFirmwareResponse]:
    _ = current_user
    firmwares = await list_firmwares(db)
    return [_firmware_response(fw) for fw in firmwares]


@router.delete(
    "/firmware/{firmware_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a firmware build",
)
async def delete_firmware_build(
    firmware_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Response:
    _require_admin(current_user)
    fw = await get_firmware(db, firmware_id)
    if fw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware not found")
    await delete_firmware(db, fw)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/firmware/{firmware_id}/deploy/{device_id}",
    response_model=OtaDeployResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger OTA update on a device",
)
async def deploy_firmware(
    firmware_id: int,
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    mqtt_client: MQTTClient = Depends(get_mqtt_client),  # noqa: B008
) -> OtaDeployResponse:
    _require_admin(current_user)

    fw = await get_firmware(db, firmware_id)
    if fw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware not found")

    device = await get_hardware_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    server_url = build_firmware_server_url(firmware_id)
    clear_ota_state(device_id)

    ota_config = {
        "serverUrl": server_url,
        "enabled": True,
        "checkOnConnect": False,
    }
    config_topic = build_device_topic(device, "config", "set", "ota")
    await mqtt_client.publish(config_topic, json.dumps(ota_config).encode())

    ota_start_topic = build_device_topic(device, "ota", "start")
    await mqtt_client.publish(ota_start_topic, b"")

    return OtaDeployResponse(
        detail="OTA deploy triggered",
        firmware_id=firmware_id,
        device_id=device_id,
        server_url=server_url,
    )


@router.get(
    "/firmware/{firmware_id}/manifest.json",
    summary="Serve OTA manifest (fetched by device)",
    include_in_schema=False,
)
async def serve_manifest(
    firmware_id: int,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Response:
    fw = await get_firmware(db, firmware_id)
    if fw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware not found")
    manifest = {
        "version": fw.version,
        "board": fw.board,
        "file": "firmware.bin",
        "md5": fw.md5,
        "size": fw.size_bytes,
    }
    return Response(content=json.dumps(manifest), media_type="application/json")


@router.get(
    "/firmware/{firmware_id}/firmware.bin",
    summary="Serve OTA firmware binary (fetched by device)",
    include_in_schema=False,
)
async def serve_binary(
    firmware_id: int,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> FileResponse:
    fw = await get_firmware(db, firmware_id)
    if fw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware not found")
    path = firmware_file_path(fw.filename)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Firmware binary not found on disk",
        )
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename="firmware.bin",
    )


@router.get(
    "/status/{device_id}",
    response_model=OtaStatusResponse,
    summary="Get latest OTA result reported by a device",
)
async def get_device_ota_status(
    device_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> OtaStatusResponse:
    _ = current_user
    state = get_ota_state(device_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OTA result available for this device",
        )
    return OtaStatusResponse(
        state=state["state"],
        payload=state["payload"],
        timestamp=state["timestamp"],
        progress=state.get("progress"),
    )
