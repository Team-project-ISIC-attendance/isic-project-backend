from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from loguru import logger

from src.api.routes import router
from src.config import settings
from src.database.connection import AsyncSessionLocal, engine
from src.mqtt.client import MQTTClient
from src.mqtt.handler import handle_mqtt_message


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

app.include_router(router)


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.http_host,
        port=settings.http_port,
        reload=settings.debug,
    )

