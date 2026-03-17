from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.attendance import router as attendance_router
from src.api.auth import router as auth_router
from src.api.lessons import router as lessons_router
from src.api.routes import router
from src.api.schedule import router as schedule_router
from src.api.semesters import router as semesters_router
from src.api.students import router as students_router
from src.api.subjects import router as subjects_router
from src.api.weeks import router as weeks_router
from src.config import settings
from src.database.connection import AsyncSessionLocal, engine
from src.mqtt.client import MQTTClient
from src.mqtt.handler import handle_mqtt_message
from src.services.auth_service import ensure_admin_exists


def _create_mqtt_client() -> MQTTClient:
    return MQTTClient(
        hostname=settings.mqtt_broker_host,
        port=settings.mqtt_broker_port,
        topic=settings.mqtt_topic,
        client_id=settings.mqtt_client_id,
        session_factory=AsyncSessionLocal,
    )


async def _startup_application() -> MQTTClient:
    logger.info("Starting application...")
    mqtt_client = _create_mqtt_client()
    await mqtt_client.start(handle_mqtt_message)
    logger.info("MQTT client started")
    async with AsyncSessionLocal() as session:
        await ensure_admin_exists(session)
    logger.info("Admin user ensured")
    return mqtt_client


async def _shutdown_application(mqtt_client: MQTTClient) -> None:
    logger.info("Shutting down application...")
    await mqtt_client.stop()
    await engine.dispose()
    logger.info("Application stopped")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    mqtt_client = await _startup_application()
    yield
    await _shutdown_application(mqtt_client)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(attendance_router)
app.include_router(auth_router)
app.include_router(lessons_router)
app.include_router(router)
app.include_router(semesters_router)
app.include_router(students_router)
app.include_router(subjects_router)
app.include_router(schedule_router)
app.include_router(weeks_router)


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.http_host,
        port=settings.http_port,
        reload=settings.debug,
    )

