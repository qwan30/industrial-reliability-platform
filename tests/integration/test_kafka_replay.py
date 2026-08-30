from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import datetime
from itertools import islice
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tests.helpers_replay import make_sample_replay_command
from tests.test_replay import _create_mock_parquet

from industrial_reliability.kafka_io import (
    KafkaSettings,
    decode_message,
    encode_message,
)
from industrial_reliability.persistence import RuntimeStore
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
    require_live = os.environ.get("REQUIRE_INTEGRATION_SERVICES", "").lower() in ("true", "1")
    try:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

        producer = AIOKafkaProducer(bootstrap_servers="localhost:29092")
        await asyncio.wait_for(producer.start(), timeout=1.5)
        await producer.stop()
    except Exception as exc:
        if require_live:
            raise RuntimeError(
                f"Required integration Kafka unavailable at localhost:29092: {exc}"
            ) from exc
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


@pytest.fixture
def store() -> RuntimeStore:
    require_live = os.environ.get("REQUIRE_INTEGRATION_SERVICES", "").lower() in ("true", "1")
    test_db_url = os.environ.get("DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp")
    try:
        st = RuntimeStore(test_db_url)
        st.check_connection()
        migration_sql_001 = Path("db/migrations/001_alert_lifecycle.sql").read_text(
            encoding="utf-8"
        )
        st.execute_script(migration_sql_001)
        migration_sql_004 = Path("db/migrations/004_alert_runtime_state.sql").read_text(
            encoding="utf-8"
        )
        st.execute_script(migration_sql_004)
        return st
    except Exception as exc:
        if require_live:
            raise RuntimeError(
                f"Required integration database unavailable at {test_db_url}: {exc}"
            ) from exc
        pytest.skip("PostgreSQL unavailable at " + test_db_url)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_replay_resumes_from_durable_checkpoint(
    store: RuntimeStore,
    tmp_path: Path,
) -> None:
    parquet_path = _create_mock_parquet(tmp_path, n_rows=50)
    source = ReplaySource(parquet_path, expected_contract_sha256="b" * 64)
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
        range_start=datetime(2020, 3, 1),
        range_end=datetime(2020, 3, 1, 1),
        source_dataset_sha256=source.identity.source_dataset_sha256,
        contract_sha256=source.identity.contract_sha256,
    )
    first_batch = list(islice(source.iter_events(command), 25))
    store.record_replay_checkpoint(
        command=command,
        state="RUNNING",
        last_sequence=first_batch[-1].sequence,
        source_timestamp=first_batch[-1].source_timestamp,
    )
    incomplete_replays = [
        r
        for r in store.load_incomplete_replays()
        if r.replay_session_id == command.replay_session_id
    ]
    assert len(incomplete_replays) == 1
    checkpoint = incomplete_replays[0]
    service = ReplayService(
        KafkaSettings("localhost:29092"),
        source,
        store=store,
        enable_pacing=False,
    )
    service.producer = AsyncMock()
    await service.resume_checkpoint(checkpoint)

    payloads = [
        decode_message(call.kwargs["value"], TelemetryEventV1)
        for call in service.producer.send_and_wait.await_args_list
        if call.args[0] == TELEMETRY_TOPIC
    ]
    assert payloads[0].sequence == 26
    assert payloads[0].source_timestamp > first_batch[-1].source_timestamp
    assert [event.sequence for event in payloads] == list(range(26, payloads[-1].sequence + 1))
    assert store.load_replay_checkpoint(command.replay_session_id).state == "COMPLETED"
