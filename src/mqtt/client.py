import asyncio
from collections.abc import Awaitable, Callable

from aiomqtt import Client, MqttError
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

RECONNECT_DELAY_SECONDS = 5


def _convert_payload_to_bytes(payload: bytes | bytearray | str | object) -> bytes:
    if isinstance(payload, bytes):
        return payload
    elif isinstance(payload, bytearray):
        return bytes(payload)
    elif isinstance(payload, str):
        return payload.encode("utf-8")
    else:
        return str(payload).encode("utf-8")


class MQTTClient:
    def __init__(
        self,
        hostname: str,
        port: int,
        topic: str,
        client_id: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._hostname = hostname
        self._port = port
        self._topic = topic
        self._client_id = client_id
        self._session_factory = session_factory
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(
        self,
        message_handler: Callable[
            [AsyncSession, str, bytes], Awaitable[None]
        ],
    ) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run(message_handler))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(
        self,
        message_handler: Callable[
            [AsyncSession, str, bytes], Awaitable[None]
        ],
    ) -> None:
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
        message_handler: Callable[
            [AsyncSession, str, bytes], Awaitable[None]
        ],
    ) -> None:
        client = Client(
            hostname=self._hostname,
            port=self._port,
            identifier=self._client_id,
        )
        try:
            async with client:
                await self._subscribe(client)
                await self._process_messages(client, message_handler)
        except asyncio.CancelledError:
            logger.info("Connection cancelled")
            raise

    async def _subscribe(self, client: Client) -> None:
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
        message_handler: Callable[
            [AsyncSession, str, bytes], Awaitable[None]
        ],
    ) -> None:
        try:
            async for message in client.messages:
                if not self._running:
                    break
                payload = _convert_payload_to_bytes(message.payload)
                await self._handle_message(message_handler, message.topic.value, payload)
        except asyncio.CancelledError:
            logger.info("Message processing cancelled")
            raise

    async def _handle_message(
        self,
        message_handler: Callable[
            [AsyncSession, str, bytes], Awaitable[None]
        ],
        topic: str,
        payload: bytes,
    ) -> None:
        async with self._session_factory() as session:
            await message_handler(session, topic, payload)

    async def _handle_mqtt_error(self, error: MqttError) -> None:
        logger.error("MQTT error occurred")
        await self._schedule_reconnect()

    async def _handle_connection_error(
        self, error: OSError | ConnectionError
    ) -> None:
        logger.error("Connection error in MQTT client")
        await self._schedule_reconnect()

    async def _schedule_reconnect(self) -> None:
        if not self._running:
            return
        logger.info(
            "Reconnecting in {} seconds...", RECONNECT_DELAY_SECONDS
        )
        for _ in range(int(RECONNECT_DELAY_SECONDS * 10)):
            if not self._running:
                return
            await asyncio.sleep(0.1)

