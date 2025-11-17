import asyncio
import os
import socket
import tempfile
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.core.container import DockerContainer

# Set required config values for tests before importing settings
os.environ.setdefault("HTTP_HOST", "localhost")
os.environ.setdefault("HTTP_PORT", "8000")

from loguru import logger

from src.config import settings
from src.database.connection import get_db
from src.main import app
from src.models.base import Base
from src.mqtt.client import MQTTClient
from src.mqtt.handler import handle_mqtt_message

MQTT_BROKER_IMAGE = "eclipse-mosquitto:2.0.18"
MQTT_BROKER_COMMAND = "mosquitto -c /mosquitto-no-auth.conf"
MQTT_PORT_CHECK_TIMEOUT_SECONDS = 30
MQTT_PORT_CHECK_INTERVAL_SECONDS = 0.5
SOCKET_TIMEOUT_SECONDS = 1
MQTT_CLIENT_CONNECTION_DELAY_SECONDS = 1.0
MQTT_CLIENT_STOP_TIMEOUT_SECONDS = 5.0
TEST_CLIENT_ID_PREFIX = "test-client"
TEST_MQTT_TOPIC = "isic/scan"
DATABASE_FILE_SUFFIX = ".db"
SOCKET_CONNECTION_SUCCESS = 0


def check_port_is_open(host: str, port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT_SECONDS)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == SOCKET_CONNECTION_SUCCESS
    except Exception:
        return False


def wait_for_mqtt_port(
    host: str, port: int,
    timeout: int = MQTT_PORT_CHECK_TIMEOUT_SECONDS
) -> None:
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_port_is_open(host, port):
            return
        time.sleep(MQTT_PORT_CHECK_INTERVAL_SECONDS)
    raise TimeoutError(
        f"MQTT broker did not become ready within {timeout} seconds"
    )


def create_mqtt_container() -> DockerContainer:
    return (
        DockerContainer(MQTT_BROKER_IMAGE)
        .with_exposed_ports(settings.mqtt_broker_port)
        .with_command(MQTT_BROKER_COMMAND)
    )


def create_database_url_from_path(db_path: str) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def create_test_session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def mqtt_container() -> Generator[DockerContainer]:
    container = create_mqtt_container()
    container.start()
    host = cast(str, container.get_container_host_ip())
    port = int(container.get_exposed_port(settings.mqtt_broker_port))
    wait_for_mqtt_port(
        host, port, timeout=MQTT_PORT_CHECK_TIMEOUT_SECONDS
    )
    yield container
    container.stop()


@pytest.fixture
def mqtt_host(mqtt_container: DockerContainer) -> str:
    return cast(str, mqtt_container.get_container_host_ip())


@pytest.fixture
def mqtt_port(mqtt_container: DockerContainer) -> int:
    return int(mqtt_container.get_exposed_port(settings.mqtt_broker_port))


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    with tempfile.NamedTemporaryFile(
        suffix=DATABASE_FILE_SUFFIX, delete=False
    ) as tmp_file:
        db_path = tmp_file.name

    try:
        engine = create_async_engine(
            create_database_url_from_path(db_path),
            echo=False,
            future=True,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        await engine.dispose()
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest_asyncio.fixture
async def db_session(
    db_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession]:
    async_session_maker = create_test_session_factory(db_engine)
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def mqtt_client(
    mqtt_host: str,
    mqtt_port: int,
    db_engine: AsyncEngine,
    request: pytest.FixtureRequest,
) -> AsyncGenerator[MQTTClient]:
    test_name = request.node.name if hasattr(request, "node") else "test"
    client_id = f"{TEST_CLIENT_ID_PREFIX}-{test_name}"
    
    async_session_maker = create_test_session_factory(db_engine)
    client = MQTTClient(
        hostname=mqtt_host,
        port=mqtt_port,
        topic=TEST_MQTT_TOPIC,
        client_id=client_id,
        session_factory=async_session_maker,
    )
    await client.start(handle_mqtt_message)
    await asyncio.sleep(MQTT_CLIENT_CONNECTION_DELAY_SECONDS)
    try:
        yield client
    finally:
        try:
            await asyncio.wait_for(
                client.stop(), timeout=MQTT_CLIENT_STOP_TIMEOUT_SECONDS
            )
        except TimeoutError:
            logger.warning("MQTT client stop timed out, forcing cleanup")
            await asyncio.sleep(0.1)


@pytest_asyncio.fixture
async def test_client(
    db_engine: AsyncEngine,
) -> AsyncGenerator[AsyncClient]:
    async_session_maker = create_test_session_factory(db_engine)

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        async with async_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()

