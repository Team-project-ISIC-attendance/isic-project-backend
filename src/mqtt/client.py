"""Async MQTT client."""

import asyncio
from collections.abc import Awaitable, Callable

from aiomqtt import Client, MqttError
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_RECONNECT_DELAY = 5


class MQTTClient:
    """Async MQTT client for receiving ISIC scan messages."""

    def __init__(
        self,
        hostname: str,
        port: int,
        topic: str,
        client_id: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Initialize MQTT client with required dependencies."""
        self._hostname = hostname
        self._port = port
        self._topic = topic
        self._client_id = client_id
        self._session_factory = session_factory
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(
        self,
        message_handler: Callable[[AsyncSession, str, bytes], Awaitable[None]],
    ) -> None:
        """Start MQTT client and subscribe to topic."""
        self._running = True
        self._task = asyncio.create_task(self._run(message_handler))

    async def stop(self) -> None:
        """Stop MQTT client."""
        self._running = False
        if self._task:
            await self._task

    async def _run(
        self,
        message_handler: Callable[[AsyncSession, str, bytes], Awaitable[None]],
    ) -> None:
        """Run MQTT client loop."""
        while self._running:
            try:
                await self._connect_and_listen(message_handler)
            except MqttError as e:
                await self._handle_mqtt_error(e)
            except (OSError, ConnectionError) as e:
                await self._handle_connection_error(e)
            except asyncio.CancelledError:
                logger.info("MQTT client task cancelled")
                raise

    async def _connect_and_listen(
        self,
        message_handler: Callable[[AsyncSession, str, bytes], Awaitable[None]],
    ) -> None:
        """Connect to broker and listen for messages."""
        client = Client(
            hostname=self._hostname,
            port=self._port,
            identifier=self._client_id,
        )
        async with client:
            await self._subscribe(client)
            await self._process_messages(client, message_handler)

    async def _subscribe(self, client: Client) -> None:
        """Subscribe to configured topic."""
        logger.info(
            "Connected to MQTT broker at {}:{}",
            self._hostname,
            self._port,
        )
        await client.subscribe(self._topic)
        logger.info("Subscribed to topic: {}", self._topic)

    async def _process_messages(
        self,
        client: Client,
        message_handler: Callable[[AsyncSession, str, bytes], Awaitable[None]],
    ) -> None:
        """Process incoming MQTT messages."""
        async for message in client.messages:
            if not self._running:
                break
            await self._handle_message(message_handler, message.topic.value, message.payload)

    async def _handle_message(
        self,
        message_handler: Callable[[AsyncSession, str, bytes], Awaitable[None]],
        topic: str,
        payload: bytes,
    ) -> None:
        """Handle a single MQTT message."""
        async with self._session_factory() as session:
            await message_handler(session, topic, payload)

    async def _handle_mqtt_error(self, error: MqttError) -> None:
        """Handle MQTT-specific errors."""
        logger.error("MQTT error occurred")
        await self._schedule_reconnect()

    async def _handle_connection_error(self, error: OSError | ConnectionError) -> None:
        """Handle connection-related errors."""
        logger.error("Connection error in MQTT client")
        await self._schedule_reconnect()

    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection attempt."""
        if self._running:
            logger.info("Reconnecting in {} seconds...", _RECONNECT_DELAY)
            await asyncio.sleep(_RECONNECT_DELAY)

