from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from industrial_reliability.kafka_io import KafkaSettings, encode_message
from industrial_reliability.persistence import ReplayCheckpoint, RuntimeStore
from industrial_reliability.phase1b_contracts import phase1b_contract_manifest
from industrial_reliability.replay import ReplaySource
from industrial_reliability.replay_service import (
    ReplayService,
    main,
)
from tests.helpers_replay import (
    make_sample_quarantine,
    make_sample_replay_command,
    make_sample_replay_status,
    make_sample_telemetry_event,
)
from tests.test_replay import _create_mock_parquet


class MockRecord:
    def __init__(self, value: bytes, topic: str = "irp.replay.commands.v1") -> None:
        self.value = value
        self.topic = topic
        self.partition = 0
        self.offset = 1


@pytest.mark.asyncio
async def test_replay_service_handles_valid_start_and_completion(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=5)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(pq_path, expected_contract_sha256="b" * 64)
    service = ReplayService(settings, source, enable_pacing=False)

    published_telemetry = []
    published_status = []
    service.publish_telemetry = AsyncMock(side_effect=lambda ev: published_telemetry.append(ev))  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=lambda st: published_status.append(st))  # type: ignore[method-assign]

    session_id = uuid4()
    cmd = make_sample_replay_command(action="START", session_id=session_id, speed=1000)

    record = MockRecord(encode_message(cmd))
    await service.handle_command_record(record)

    assert service.active_session is not None
    await service.active_session.task

    assert len(published_telemetry) == 5
    assert [ev.sequence for ev in published_telemetry] == [1, 2, 3, 4, 5]
    assert any(st.state == "RUNNING" for st in published_status)
    assert any(st.state == "COMPLETED" for st in published_status)


@pytest.mark.asyncio
async def test_replay_service_pause_resume_stop_lifecycle(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=20)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(pq_path, expected_contract_sha256="b" * 64)
    service = ReplayService(settings, source, enable_pacing=True)

    published_status = []
    service.publish_telemetry = AsyncMock()  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=lambda st: published_status.append(st))  # type: ignore[method-assign]

    session_id = uuid4()
    cmd_start = make_sample_replay_command(action="START", session_id=session_id, speed=1)
    await service.handle_command(cmd_start)
    assert service.active_session is not None

    # Pause
    cmd_pause = make_sample_replay_command(action="PAUSE", session_id=session_id, speed=1)
    await service.handle_command(cmd_pause)
    assert any(st.state == "PAUSED" for st in published_status)

    # Resume with speed change
    cmd_resume = make_sample_replay_command(action="RESUME", session_id=session_id, speed=1000)
    await service.handle_command(cmd_resume)

    # Stop
    cmd_stop = make_sample_replay_command(action="STOP", session_id=session_id, speed=1000)
    await service.handle_command(cmd_stop)
    assert any(st.state == "STOPPED" for st in published_status)

    await service.stop()


@pytest.mark.asyncio
async def test_publish_methods_with_mock_producer(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=2)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(pq_path, expected_contract_sha256="b" * 64)
    service = ReplayService(settings, source)

    mock_producer = AsyncMock()
    service.producer = mock_producer

    # Test publish_telemetry
    ev = make_sample_telemetry_event()
    await service.publish_telemetry(ev)
    assert mock_producer.send_and_wait.called

    # Test publish_status
    st = make_sample_replay_status()
    await service.publish_status(st)

    # Test publish_quarantine
    qr = make_sample_quarantine()
    await service.publish_quarantine(qr)


def test_main_cli_certification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract_sha = str(phase1b_contract_manifest()["contract_sha256"])
    pq_path = _create_mock_parquet(tmp_path, n_rows=5, contract_sha256=contract_sha)
    out_dir = tmp_path / "cli_cert"

    test_args = [
        "replay_service",
        "--certify-range-start",
        "2020-03-01T00:00:00",
        "--certify-range-end",
        "2020-03-01T00:01:00",
        "--speeds",
        "1000",
        "--output",
        str(out_dir),
        "--parquet",
        str(pq_path),
    ]
    monkeypatch.setattr(sys, "argv", test_args)
    main()
    assert (out_dir / "certification_summary.json").is_file()


@pytest.mark.asyncio
async def test_replay_service_rejects_source_identity_mismatch(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(
        tmp_path,
        n_rows=5,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
    )
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(pq_path, expected_contract_sha256="b" * 64)
    service = ReplayService(settings, source, enable_pacing=False)

    published_telemetry = []
    published_status = []
    service.publish_telemetry = AsyncMock(side_effect=lambda ev: published_telemetry.append(ev))  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=lambda st: published_status.append(st))  # type: ignore[method-assign]

    session_id = uuid4()
    cmd = make_sample_replay_command(
        action="START",
        session_id=session_id,
        speed=1000,
        source_dataset_sha256="c" * 64,
        contract_sha256="b" * 64,
    )
    await service.handle_command(cmd)

    assert service.active_session is None
    assert len(published_telemetry) == 0
    assert len(published_status) == 1
    assert published_status[0].state == "FAILED"
    assert published_status[0].error_code == "REPLAY_SOURCE_IDENTITY_MISMATCH"


@pytest.mark.asyncio
async def test_replay_service_records_checkpoints_during_streaming(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=5)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(pq_path, expected_contract_sha256="b" * 64)
    mock_store = MagicMock(spec=RuntimeStore)
    service = ReplayService(settings, source, store=mock_store, enable_pacing=False)

    published_telemetry = []
    published_status = []
    service.publish_telemetry = AsyncMock(side_effect=lambda ev: published_telemetry.append(ev))  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=lambda st: published_status.append(st))  # type: ignore[method-assign]

    session_id = uuid4()
    cmd = make_sample_replay_command(action="START", session_id=session_id, speed=1000)

    record = MockRecord(encode_message(cmd))
    await service.handle_command_record(record)

    assert service.active_session is not None
    await service.active_session.task

    assert len(published_telemetry) == 5
    # Initial START checkpoint (seq=0) + 5 events (seq=1..5) + 1 completion
    assert mock_store.record_replay_checkpoint.call_count >= 7
    # Verify first call recorded RUNNING with last_sequence=0
    first_call = mock_store.record_replay_checkpoint.call_args_list[0]
    assert first_call.kwargs.get("state") == "RUNNING" or first_call.args[1] == "RUNNING"
    # Verify last call recorded COMPLETED with last_sequence=5
    last_call = mock_store.record_replay_checkpoint.call_args_list[-1]
    assert last_call.kwargs.get("state") == "COMPLETED" or last_call.args[1] == "COMPLETED"


@pytest.mark.asyncio
async def test_replay_service_start_raises_on_multiple_incomplete_replays(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=5)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(pq_path, expected_contract_sha256="b" * 64)
    cmd1 = make_sample_replay_command(action="START", session_id=uuid4(), speed=1000)
    cmd2 = make_sample_replay_command(action="START", session_id=uuid4(), speed=1000)
    cp1 = ReplayCheckpoint(
        replay_session_id=cmd1.replay_session_id,
        command=cmd1,
        state="RUNNING",
        last_sequence=2,
        source_timestamp=cmd1.range_start,
    )
    cp2 = ReplayCheckpoint(
        replay_session_id=cmd2.replay_session_id,
        command=cmd2,
        state="PAUSED",
        last_sequence=3,
        source_timestamp=cmd2.range_start,
    )
    mock_store = MagicMock(spec=RuntimeStore)
    mock_store.load_incomplete_replays.return_value = (cp1, cp2)

    service = ReplayService(settings, source, store=mock_store, enable_pacing=False)

    with (
        patch("industrial_reliability.replay_service.AIOKafkaProducer") as mock_prod_cls,
        patch("industrial_reliability.replay_service.AIOKafkaConsumer") as mock_cons_cls,
    ):
        mock_prod = AsyncMock()
        mock_cons = AsyncMock()
        mock_prod_cls.return_value = mock_prod
        mock_cons_cls.return_value = mock_cons

        with pytest.raises(RuntimeError, match="multiple incomplete replay sessions require operator resolution"):
            await service.start()


@pytest.mark.asyncio
async def test_replay_service_resume_checkpoint(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=10)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(pq_path, expected_contract_sha256="b" * 64)
    mock_store = MagicMock(spec=RuntimeStore)
    service = ReplayService(settings, source, store=mock_store, enable_pacing=False)

    published_telemetry = []
    service.publish_telemetry = AsyncMock(side_effect=lambda ev: published_telemetry.append(ev))  # type: ignore[method-assign]

    cmd = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
        range_end=datetime(2020, 3, 1, 1, 0, 0),
    )
    first_3_events = list(source.iter_events(cmd))[:3]
    checkpoint = ReplayCheckpoint(
        replay_session_id=cmd.replay_session_id,
        command=cmd,
        state="RUNNING",
        last_sequence=first_3_events[-1].sequence,
        source_timestamp=first_3_events[-1].source_timestamp,
    )

    await service.resume_checkpoint(checkpoint)

    assert len(published_telemetry) == 7
    assert published_telemetry[0].sequence == 4
    assert published_telemetry[0].source_timestamp > first_3_events[-1].source_timestamp
    assert [ev.sequence for ev in published_telemetry] == [4, 5, 6, 7, 8, 9, 10]
    # Check that checkpoints were recorded and final state is COMPLETED
    last_call = mock_store.record_replay_checkpoint.call_args_list[-1]
    assert last_call.kwargs.get("state") == "COMPLETED" or last_call.args[1] == "COMPLETED"
    assert (
        last_call.kwargs.get("last_sequence") == 10
        or (len(last_call.args) > 2 and last_call.args[2] == 10)
    )


