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
from industrial_reliability.package_champion import build_champion_package
from industrial_reliability.runtime_kafka import (
    AioKafkaCommandProducer,
    CommandProducer,
    InMemoryCommandProducer,
)
from industrial_reliability.runtime_messages import (
    REPLAY_COMMANDS_TOPIC,
    ReplayCommandV1,
)
from tests.test_package_champion import _create_mock_feasible_phase1b_run


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
    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    pkg_dir = tmp_path / "pkg"
    build_result = build_champion_package(run_dir, feat_path, pkg_dir)
    scorer = load_champion(pkg_dir, build_result.manifest_sha256)

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
