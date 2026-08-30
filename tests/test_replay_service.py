from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from industrial_reliability.kafka_io import KafkaSettings, encode_message
from industrial_reliability.persistence import ReplayCheckpoint, RuntimeStore
from industrial_reliability.phase1b_contracts import metropt3_contract_manifest
from industrial_reliability.phase1b_data import sha256_file
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
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
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
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    store = MagicMock(spec=RuntimeStore)
    service = ReplayService(settings, source, store=store, enable_pacing=True)

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

    assert [call.args[1] for call in store.update_replay_checkpoint_state.call_args_list] == [
        "PAUSED",
        "RUNNING",
        "STOPPED",
    ]


@pytest.mark.asyncio
async def test_paused_checkpoint_waits_until_resume(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=10)
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
        range_end=datetime(2020, 3, 1, 1),
    )
    first_three = list(source.iter_events(command))[:3]
    checkpoint = ReplayCheckpoint(
        replay_session_id=command.replay_session_id,
        command=command,
        state="PAUSED",
        last_sequence=3,
        source_timestamp=first_three[-1].source_timestamp,
    )
    store = MagicMock(spec=RuntimeStore)
    store.load_incomplete_replays.return_value = (checkpoint,)
    service = ReplayService(
        KafkaSettings("localhost:9092"),
        source,
        store=store,
        enable_pacing=False,
    )
    telemetry = []
    service.publish_telemetry = AsyncMock(side_effect=telemetry.append)  # type: ignore[method-assign]
    service.publish_status = AsyncMock()  # type: ignore[method-assign]

    with (
        patch("industrial_reliability.replay_service.AIOKafkaProducer") as producer_cls,
        patch("industrial_reliability.replay_service.AIOKafkaConsumer") as consumer_cls,
    ):
        producer_cls.return_value = AsyncMock()
        consumer_cls.return_value = AsyncMock()
        await service.start()
        assert service.active_session is not None
        await asyncio.sleep(0)
        assert service.active_session.controller.state == "PAUSED"
        assert telemetry == []

        resume = make_sample_replay_command(
            action="RESUME",
            session_id=command.replay_session_id,
            speed=1000,
        )
        await service.handle_command(resume)
        await service.active_session.task
        assert telemetry[0].sequence == 4
        assert telemetry[0].source_timestamp > first_three[-1].source_timestamp
        await service.stop()


@pytest.mark.asyncio
async def test_publish_methods_with_mock_producer(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=2)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
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
    contract_manifest = metropt3_contract_manifest()
    contract_sha = str(contract_manifest["contract_sha256"])
    source_sha = str(contract_manifest["archive_sha256"])
    pq_path = _create_mock_parquet(
        tmp_path,
        n_rows=5,
        source_dataset_sha256=source_sha,
        contract_sha256=contract_sha,
    )
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
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
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
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
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
async def test_start_checkpoint_has_no_cursor_before_first_publish(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=5)
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    store = MagicMock(spec=RuntimeStore)
    service = ReplayService(
        KafkaSettings("localhost:9092"),
        source,
        store=store,
        enable_pacing=False,
    )
    service.publish_telemetry = AsyncMock(side_effect=RuntimeError("simulated crash"))  # type: ignore[method-assign]
    service.publish_status = AsyncMock()  # type: ignore[method-assign]
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
    )

    await service.handle_command(command)
    assert service.active_session is not None
    await service.active_session.task

    initial = store.record_replay_checkpoint.call_args_list[0]
    assert initial.args == (command, "RUNNING", 0, None)


@pytest.mark.asyncio
async def test_resume_from_zero_replays_range_start_and_publishes_completed(
    tmp_path: Path,
) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=6)
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    store = MagicMock(spec=RuntimeStore)
    service = ReplayService(
        KafkaSettings("localhost:9092"),
        source,
        store=store,
        enable_pacing=False,
    )
    telemetry = []
    statuses = []
    service.publish_telemetry = AsyncMock(side_effect=telemetry.append)  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=statuses.append)  # type: ignore[method-assign]
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
    )
    expected = list(source.iter_events(command))
    checkpoint = ReplayCheckpoint(
        replay_session_id=command.replay_session_id,
        command=command,
        state="RUNNING",
        last_sequence=0,
        source_timestamp=None,
    )

    await service.resume_checkpoint(checkpoint)

    assert [(event.sequence, event.source_timestamp) for event in telemetry] == [
        (event.sequence, event.source_timestamp) for event in expected
    ]
    assert statuses[-1].state == "COMPLETED"
    assert statuses[-1].last_sequence == len(expected)


@pytest.mark.asyncio
async def test_resume_failure_records_and_publishes_failed(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=3)
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    store = MagicMock(spec=RuntimeStore)
    service = ReplayService(
        KafkaSettings("localhost:9092"),
        source,
        store=store,
        enable_pacing=False,
    )
    statuses = []
    service.publish_telemetry = AsyncMock(side_effect=RuntimeError("publish failed"))  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=statuses.append)  # type: ignore[method-assign]
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
    )
    checkpoint = ReplayCheckpoint(
        replay_session_id=command.replay_session_id,
        command=command,
        state="RUNNING",
        last_sequence=0,
        source_timestamp=None,
    )

    await service.resume_checkpoint(checkpoint)

    failed = store.record_replay_checkpoint.call_args_list[-1]
    assert failed.kwargs["state"] == "FAILED"
    assert statuses[-1].state == "FAILED"
    assert statuses[-1].error_code == "REPLAY_STREAM_ERROR"


@pytest.mark.asyncio
async def test_replay_service_start_raises_on_multiple_incomplete_replays(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=5)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
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

        with pytest.raises(
            RuntimeError, match="multiple incomplete replay sessions require operator resolution"
        ):
            await service.start()


@pytest.mark.asyncio
async def test_replay_service_resume_checkpoint(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=10)
    settings = KafkaSettings(bootstrap_servers="localhost:9092")
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    mock_store = MagicMock(spec=RuntimeStore)
    service = ReplayService(settings, source, store=mock_store, enable_pacing=False)

    published_telemetry = []
    service.publish_telemetry = AsyncMock(side_effect=lambda ev: published_telemetry.append(ev))  # type: ignore[method-assign]
    service.publish_status = AsyncMock()  # type: ignore[method-assign]

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
    assert last_call.kwargs.get("last_sequence") == 10 or (
        len(last_call.args) > 2 and last_call.args[2] == 10
    )


def test_main_default_uses_package_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from industrial_reliability.package_champion import ChampionManifest

    source_sha = "a" * 64
    contract_sha = "b" * 64
    pq_path = _create_mock_parquet(
        tmp_path,
        n_rows=5,
        source_dataset_sha256=source_sha,
        contract_sha256=contract_sha,
    )
    output_sha = sha256_file(pq_path)

    pkg_manifest_data = {
        "schema_version": "champion-package-v2",
        "package_role": "CHAMPION",
        "evaluation_verdict": "FEASIBLE",
        "operational_status": "PRODUCTION_CANDIDATE",
        "source_champion_schema": "phase1b-champion-v1",
        "source_run_id": "run-123",
        "model_id": "statistical",
        "model_version": "champion-statistical-v1",
        "contract_sha256": contract_sha,
        "source_dataset_sha256": source_sha,
        "prepared_output_sha256": output_sha,
        "feature_output_sha256": "f" * 64,
        "feature_names": ["tp2"],
        "threshold": 1.5,
        "threshold_provenance": {
            "split": "calibration",
            "quantile": 0.995,
            "method": "higher",
        },
        "golden_case_count": 3,
        "artifact_sha256": {
            "detector.joblib": "d" * 64,
            "evidence-baseline.npz": "e" * 64,
            "golden-cases.json": "g" * 64,
            "drift-reference.json": "r" * 64,
        },
    }
    manifest_file = tmp_path / "pkg_manifest.json"
    manifest_file.write_text(json.dumps(pkg_manifest_data), encoding="utf-8")

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("REPLAY_PACKAGE_MANIFEST", str(manifest_file))
    monkeypatch.setattr(sys, "argv", ["replay_service", "--parquet", str(pq_path)])

    def _fake_run(coro: object) -> None:
        if hasattr(coro, "close"):
            coro.close()

    with patch("industrial_reliability.replay_service.asyncio.run", side_effect=_fake_run) as mock_run:
        main()
        assert mock_run.called
