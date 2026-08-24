from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from industrial_reliability.kafka_io import KafkaSettings, encode_message
from industrial_reliability.replay import ReplaySource
from industrial_reliability.replay_service import (
    ReplayService,
    main,
)
from industrial_reliability.runtime_messages import (
    QuarantineRecordV1,
    ReplayCommandV1,
    ReplayStatusV1,
    TelemetryEventV1,
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
    source = ReplaySource(pq_path)
    service = ReplayService(settings, source, enable_pacing=False)

    published_telemetry = []
    published_status = []
    service.publish_telemetry = AsyncMock(side_effect=lambda ev: published_telemetry.append(ev))  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=lambda st: published_status.append(st))  # type: ignore[method-assign]

    session_id = uuid4()
    cmd = ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0, 0),
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="START",
        speed=1000,
        range_start=datetime(2020, 3, 1, 0, 0, 0),
        range_end=datetime(2020, 3, 1, 0, 1, 0),
    )

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
    source = ReplaySource(pq_path)
    service = ReplayService(settings, source, enable_pacing=True)

    published_status = []
    service.publish_telemetry = AsyncMock()  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=lambda st: published_status.append(st))  # type: ignore[method-assign]

    session_id = uuid4()
    cmd_start = ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0, 0),
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="START",
        speed=1,
        range_start=datetime(2020, 3, 1, 0, 0, 0),
        range_end=datetime(2020, 3, 1, 0, 10, 0),
    )
    await service.handle_command(cmd_start)
    assert service.active_session is not None

    # Pause
    cmd_pause = ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0, 10),
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="PAUSE",
        speed=1,
    )
    await service.handle_command(cmd_pause)
    assert any(st.state == "PAUSED" for st in published_status)

    # Resume with speed change
    cmd_resume = ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0, 10),
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="RESUME",
        speed=1000,
    )
    await service.handle_command(cmd_resume)

    # Stop
    cmd_stop = ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0, 20),
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="STOP",
        speed=1000,
    )
    await service.handle_command(cmd_stop)
    assert any(st.state == "STOPPED" for st in published_status)

    await service.stop()


@pytest.mark.asyncio
async def test_publish_methods_with_mock_producer(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=2)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(pq_path)
    service = ReplayService(settings, source)

    mock_producer = AsyncMock()
    service.producer = mock_producer

    # Test publish_telemetry
    ev = TelemetryEventV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        machine_id="compressor-01",
        sequence=1,
        tp2=1.0,
        tp3=2.0,
        h1=3.0,
        dv_pressure=4.0,
        reservoirs=5.0,
        oil_temperature=6.0,
        motor_current=7.0,
        comp=1,
        dv_electric=0,
        towers=1,
        mpg=0,
        lps=1,
        pressure_switch=0,
        oil_level=1,
        caudal_impulses=0,
    )
    await service.publish_telemetry(ev)
    assert mock_producer.send_and_wait.called

    # Test publish_status
    st = ReplayStatusV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        state="RUNNING",
        last_sequence=1,
    )
    await service.publish_status(st)

    # Test publish_quarantine
    qr = QuarantineRecordV1(
        message_id=uuid4(),
        replay_session_id=None,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        original_topic="topic",
        partition=0,
        offset=0,
        payload_sha256="c" * 64,
        error_code="ERR",
        error_detail="detail",
    )
    await service.publish_quarantine(qr)


def test_main_cli_certification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=5)
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
