"""Unit tests for Kafka command producers and replay command wiring."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from industrial_reliability.api import create_app
from industrial_reliability.champion import load_champion
from industrial_reliability.kafka_io import KafkaSettings
from industrial_reliability.runtime_kafka import (
    AioKafkaCommandProducer,
    CommandProducer,
    InMemoryCommandProducer,
)
from industrial_reliability.runtime_messages import (
    REPLAY_COMMANDS_TOPIC,
    ReplayCommandV1,
)
from tests.helpers_champion import create_mock_phase1b_champion_run


def test_command_producer_protocol_conformance() -> None:
    producer = InMemoryCommandProducer()
    assert isinstance(producer, CommandProducer)

    settings = KafkaSettings(bootstrap_servers="localhost:9092", client_id="test")
    aio_producer = AioKafkaCommandProducer(settings)
    assert isinstance(aio_producer, CommandProducer)


@pytest.mark.asyncio
async def test_in_memory_command_producer() -> None:
    producer = InMemoryCommandProducer()
    await producer.start()
    assert producer.started is True

    cmd = ReplayCommandV1(
        schema_version="replay-command-v1",
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="0" * 64,
        contract_sha256="0" * 64,
        source_timestamp=datetime(2020, 1, 1),
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="START",
        speed=100,
        range_start=datetime(2020, 1, 1),
        range_end=datetime(2020, 1, 2),
    )
    await producer.publish_command(cmd)
    assert len(producer.commands) == 1
    assert producer.commands[0] == cmd

    await producer.stop()
    assert producer.started is False


@pytest.mark.asyncio
async def test_aio_kafka_command_producer() -> None:
    settings = KafkaSettings(bootstrap_servers="localhost:9092", client_id="test")
    producer = AioKafkaCommandProducer(settings)

    mock_aio = AsyncMock()
    with patch("industrial_reliability.runtime_kafka.AIOKafkaProducer", return_value=mock_aio):
        await producer.start()
        assert producer._producer is mock_aio
        mock_aio.start.assert_awaited_once()

        cmd = ReplayCommandV1(
            schema_version="replay-command-v1",
            message_id=uuid4(),
            replay_session_id=uuid4(),
            source_dataset_sha256="0" * 64,
            contract_sha256="0" * 64,
            source_timestamp=datetime(2020, 1, 1),
            emitted_at=datetime.now(UTC),
            command_id=uuid4(),
            action="START",
            speed=100,
            range_start=datetime(2020, 1, 1),
            range_end=datetime(2020, 1, 2),
        )
        await producer.publish_command(cmd)
        mock_aio.send_and_wait.assert_awaited_once()
        call_args = mock_aio.send_and_wait.call_args
        assert call_args[0][0] == REPLAY_COMMANDS_TOPIC
        assert call_args[1]["key"] == str(cmd.replay_session_id).encode("utf-8")

        await producer.stop()
        mock_aio.stop.assert_awaited_once()


def test_api_replay_endpoints_publish_to_command_producer(tmp_path: Path) -> None:
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    scorer = load_champion(mock_run.package_dir, mock_run.manifest_sha256)

    producer = InMemoryCommandProducer()
    app = create_app(scorer, producer=producer)
    client = TestClient(app)

    # 1. Start replay
    payload_start = {
        "range_start": "2020-02-25T00:00:00",
        "range_end": "2020-02-25T01:00:00",
        "speed": 100,
    }
    r_start = client.post("/v1/replays", json=payload_start)
    assert r_start.status_code == 202
    data_start = r_start.json()
    assert data_start["success"] is True
    session_id = data_start["data"]["replay_session_id"]
    assert len(producer.commands) == 1
    assert producer.commands[0].action == "START"
    assert str(producer.commands[0].replay_session_id) == session_id

    # 2. Control replay (STOP)
    r_stop = client.post(f"/v1/replays/{session_id}/commands", json={"action": "STOP"})
    assert r_stop.status_code == 202
    assert len(producer.commands) == 2
    assert producer.commands[1].action == "STOP"
    assert str(producer.commands[1].replay_session_id) == session_id


def test_api_replay_endpoints_are_async_and_await_producer(tmp_path: Path) -> None:
    """Regression: replay endpoints must run on the app event loop.

    Sync endpoints would execute `_publish_command` in a threadpool worker with
    no running loop, forcing an ``asyncio.run`` fallback that binds the
    loop-owned aiokafka producer to a second event loop and fails at runtime.
    """
    import inspect

    mock_run = create_mock_phase1b_champion_run(tmp_path)
    scorer = load_champion(mock_run.package_dir, mock_run.manifest_sha256)
    app = create_app(scorer, producer=InMemoryCommandProducer())

    for route in app.routes:
        if route.path in {"/v1/replays", "/v1/replays/{replay_session_id}/commands"}:
            assert inspect.iscoroutinefunction(route.endpoint), (
                f"{route.path} must be an async endpoint"
            )


def test_api_replay_start_fails_closed_503_on_publish_error(tmp_path: Path) -> None:
    """Regression: a failing Kafka publish must surface 503, never a 500."""
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    scorer = load_champion(mock_run.package_dir, mock_run.manifest_sha256)

    class FailingProducer:
        async def publish_command(self, command: ReplayCommandV1) -> None:
            raise RuntimeError("Producer not started")

    app = create_app(scorer, producer=FailingProducer())
    client = TestClient(app)

    r_start = client.post(
        "/v1/replays",
        json={
            "range_start": "2020-02-25T00:00:00",
            "range_end": "2020-02-25T01:00:00",
            "speed": 100,
        },
    )
    assert r_start.status_code == 503
    assert r_start.json()["error"]["code"] == "PRODUCER_UNAVAILABLE"

    r_cmd = client.post(f"/v1/replays/{uuid4()}/commands", json={"action": "STOP"})
    assert r_cmd.status_code == 503
    assert r_cmd.json()["error"]["code"] == "PRODUCER_UNAVAILABLE"
