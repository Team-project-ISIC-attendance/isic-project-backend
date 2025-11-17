"""Main FastAPI application entrypoint."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from loguru import logger

from src.api.routes import router
from src.config import settings
from src.database.connection import AsyncSessionLocal, engine
from src.mqtt.client import MQTTClient
from src.mqtt.handler import handle_mqtt_message


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting application...")

    # Create and start MQTT client with injected dependencies
    mqtt_client = MQTTClient(
        hostname=settings.mqtt_broker_host,
        port=settings.mqtt_broker_port,
        topic=settings.mqtt_topic,
        client_id=settings.mqtt_client_id,
        session_factory=AsyncSessionLocal,
    )
    await mqtt_client.start(handle_mqtt_message)
    logger.info("MQTT client started")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    await mqtt_client.stop()
    await engine.dispose()
    logger.info("Application stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )

