"""Kafka producers and event publishers for runtime commands and console events."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol, runtime_checkable

from aiokafka import AIOKafkaProducer

from industrial_reliability.kafka_io import KafkaSettings, encode_message
from industrial_reliability.runtime_messages import (
    REPLAY_COMMANDS_TOPIC,
    ReplayCommandV1,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class CommandProducer(Protocol):
    async def publish_command(self, command: ReplayCommandV1) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class AioKafkaCommandProducer:
    def __init__(self, settings: KafkaSettings) -> None:
        self.settings = settings
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.bootstrap_servers,
            client_id=f"{self.settings.client_id}-api-command-producer",
            acks="all",
            enable_idempotence=True,
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish_command(self, command: ReplayCommandV1) -> None:
        if self._producer is None:
            raise RuntimeError("Producer not started")
        payload = encode_message(command)
        key = str(command.replay_session_id).encode("utf-8")
        await self._producer.send_and_wait(REPLAY_COMMANDS_TOPIC, value=payload, key=key)


class InMemoryCommandProducer:
    def __init__(self) -> None:
        self.commands: list[ReplayCommandV1] = []
        self.started = False

    async def start(self) -> None:
        await asyncio.sleep(0)
        self.started = True

    async def stop(self) -> None:
        await asyncio.sleep(0)
        self.started = False

    async def publish_command(self, command: ReplayCommandV1) -> None:
        await asyncio.sleep(0)
        self.commands.append(command)
