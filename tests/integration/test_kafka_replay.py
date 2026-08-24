from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from uuid import uuid4

import pytest
from tests.helpers_replay import make_sample_replay_command
from tests.test_replay import _create_mock_parquet

from industrial_reliability.kafka_io import (
    KafkaSettings,
    decode_message,
    encode_message,
)
from industrial_reliability.replay import ReplaySource
from industrial_reliability.replay_service import ReplayService
from industrial_reliability.runtime_messages import (
    REPLAY_COMMANDS_TOPIC,
    TELEMETRY_TOPIC,
    TelemetryEventV1,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kafka_replay_end_to_end(tmp_path: Path) -> None:
    try:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

        producer = AIOKafkaProducer(bootstrap_servers="localhost:29092")
        await asyncio.wait_for(producer.start(), timeout=1.5)
        await producer.stop()
    except Exception:
        pytest.skip("Kafka broker unavailable at localhost:29092")

    pq_path = _create_mock_parquet(tmp_path, n_rows=6)
    settings = KafkaSettings(bootstrap_servers="localhost:29092")
    source = ReplaySource(pq_path)
    service = ReplayService(settings, source, enable_pacing=False)

    service_task = asyncio.create_task(service.run())
    await asyncio.sleep(0.5)

    try:
        session_id = uuid4()
        cmd = make_sample_replay_command(action="START", session_id=session_id, speed=1000)

        test_producer = AIOKafkaProducer(bootstrap_servers="localhost:29092")
        await test_producer.start()
        await test_producer.send_and_wait(
            REPLAY_COMMANDS_TOPIC,
            value=encode_message(cmd),
            key=str(cmd.command_id).encode("utf-8"),
        )
        await test_producer.stop()

        consumer = AIOKafkaConsumer(
            TELEMETRY_TOPIC,
            bootstrap_servers="localhost:29092",
            group_id=f"test-consumer-{uuid4()}",
            auto_offset_reset="earliest",
        )
        await consumer.start()

        telemetry_events = []
        try:
            for _ in range(6):
                msg = await asyncio.wait_for(consumer.getone(), timeout=5.0)
                event = decode_message(msg.value, TelemetryEventV1)
                telemetry_events.append(event)
        finally:
            await consumer.stop()

        assert len(telemetry_events) == 6
        assert [ev.sequence for ev in telemetry_events] == [1, 2, 3, 4, 5, 6]

    finally:
        await service.stop()
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(service_task, timeout=2.0)
