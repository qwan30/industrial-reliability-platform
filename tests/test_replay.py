from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
import pytest

from industrial_reliability.phase1b_contracts import (
    PHASE1B_CONTRACT_SHA256,
    PHASE1B_PREPARED_OUTPUT_SHA256,
    PHASE1B_SOURCE_DATASET_SHA256,
)
from industrial_reliability.phase1b_data import sha256_file
from industrial_reliability.replay import (
    ReplayContractError,
    ReplayController,
    ReplaySource,
    pace_seconds,
)
from industrial_reliability.runtime_messages import ReplayCommandV1


def write_prepared_manifest(
    parquet: Path,
    source_dataset_sha256: str = "a" * 64,
    contract_sha256: str = "b" * 64,
) -> dict[str, str]:
    manifest = {
        "archive_sha256": source_dataset_sha256,
        "contract_sha256": contract_sha256,
        "output_sha256": sha256_file(parquet),
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    parquet.with_name("manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return manifest


def _create_mock_parquet(
    path: Path,
    n_rows: int = 20,
    source_dataset_sha256: str = "a" * 64,
    contract_sha256: str = "b" * 64,
) -> Path:
    base_ts = datetime(2020, 3, 1, 0, 0, 0)
    timestamps = [base_ts + timedelta(seconds=10 * i) for i in range(n_rows)]
    data = {
        "timestamp": timestamps,
        "tp2": [1.0 + (i % 10) * 0.1 for i in range(n_rows)],
        "tp3": [2.0 + (i % 10) * 0.1 for i in range(n_rows)],
        "h1": [3.0 + (i % 10) * 0.1 for i in range(n_rows)],
        "dv_pressure": [4.0 + (i % 10) * 0.1 for i in range(n_rows)],
        "reservoirs": [5.0 + (i % 10) * 0.1 for i in range(n_rows)],
        "oil_temperature": [50.0 + (i % 10) * 0.1 for i in range(n_rows)],
        "motor_current": [5.0 + (i % 10) * 0.1 for i in range(n_rows)],
        "comp": [1 if i % 2 == 0 else 0 for i in range(n_rows)],
        "dv_electric": [0 for _ in range(n_rows)],
        "towers": [1 for _ in range(n_rows)],
        "mpg": [0 for _ in range(n_rows)],
        "lps": [1 for _ in range(n_rows)],
        "pressure_switch": [0 for _ in range(n_rows)],
        "oil_level": [1 for _ in range(n_rows)],
        "caudal_impulses": [0 for _ in range(n_rows)],
    }
    df = pd.DataFrame(data)
    pq_path = path / "telemetry.parquet"
    df.to_parquet(pq_path, index=False)
    write_prepared_manifest(
        pq_path,
        source_dataset_sha256=source_dataset_sha256,
        contract_sha256=contract_sha256,
    )
    return pq_path


def _start_command(
    session_id: UUID,
    range_start: datetime,
    range_end: datetime,
    speed: int = 1,
) -> ReplayCommandV1:
    return ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=range_start,
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="START",
        speed=speed,  # type: ignore[arg-type]
        range_start=range_start,
        range_end=range_end,
    )


def test_pacing_changes_only_wall_clock_delay() -> None:
    previous = datetime(2020, 3, 1, 0, 0, 0)
    current = datetime(2020, 3, 1, 0, 0, 10)
    assert pace_seconds(previous, current, 1) == 10.0
    assert pace_seconds(previous, current, 100) == 0.1
    assert pace_seconds(previous, current, 1000) == 0.01

    with pytest.raises(ReplayContractError):
        pace_seconds(previous, current, 50)  # Invalid speed

    with pytest.raises(ReplayContractError):
        pace_seconds(current, previous, 1)  # Non-increasing time


def test_same_range_has_same_stream_at_every_speed(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=15)
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    session_id = uuid4()
    range_start = datetime(2020, 3, 1, 0, 0, 0)
    range_end = datetime(2020, 3, 1, 0, 2, 0)  # 12 rows (0 to 110s)

    streams = [
        list(source.iter_events(_start_command(session_id, range_start, range_end, speed=speed)))
        for speed in (1, 100, 1000)
    ]

    identities = [
        [
            (
                event.sequence,
                event.message_id,
                event.source_timestamp,
                event.tp2,
                event.comp,
            )
            for event in stream
        ]
        for stream in streams
    ]
    assert len(identities[0]) == 12
    assert identities[0] == identities[1] == identities[2]


def test_replay_controller_state_machine() -> None:
    session_id = uuid4()
    range_start = datetime(2020, 3, 1, 0, 0, 0)
    range_end = datetime(2020, 3, 1, 0, 2, 0)

    ctrl = ReplayController.created(session_id, "a" * 64, "b" * 64)
    assert ctrl.state == "CREATED"

    # Valid START
    cmd_start = _start_command(session_id, range_start, range_end, speed=100)
    ctrl = ctrl.apply(cmd_start)
    assert ctrl.state == "RUNNING"
    assert ctrl.speed == 100

    # PAUSE
    cmd_pause = ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0, 30),
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="PAUSE",
        speed=100,
    )
    ctrl = ctrl.apply(cmd_pause)
    assert ctrl.state == "PAUSED"

    # RESUME
    cmd_resume = ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0, 30),
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action="RESUME",
        speed=1000,
    )
    ctrl = ctrl.apply(cmd_resume)
    assert ctrl.state == "RUNNING"
    assert ctrl.speed == 1000

    # Complete
    ctrl = ctrl.mark_completed(12, range_end)
    assert ctrl.state == "COMPLETED"
    assert ctrl.last_sequence == 12

    status = ctrl.status()
    assert status.state == "COMPLETED"
    assert status.last_sequence == 12


def test_replay_source_uses_verified_identity(tmp_path: Path) -> None:
    parquet = _create_mock_parquet(
        tmp_path,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
    )
    source = ReplaySource(
        parquet,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(parquet),
    )
    command = _start_command(
        uuid4(),
        datetime(2020, 3, 1),
        datetime(2020, 3, 1, 0, 1),
    )
    event = next(source.iter_events(command))
    assert event.source_dataset_sha256 == source.identity.source_dataset_sha256
    assert event.contract_sha256 == source.identity.contract_sha256


def test_replay_iter_events_resumes_from_timestamp(tmp_path: Path) -> None:
    pq_path = _create_mock_parquet(tmp_path, n_rows=10)
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    session_id = uuid4()
    range_start = datetime(2020, 3, 1, 0, 0, 0)
    range_end = datetime(2020, 3, 1, 0, 2, 0)
    cmd = _start_command(session_id, range_start, range_end, speed=1000)

    all_events = list(source.iter_events(cmd))
    assert len(all_events) == 10

    # Resume from event 3 (index 2)
    resume_ts = all_events[2].source_timestamp
    resumed_events = list(
        source.iter_events(cmd, start_sequence=4, resume_from_timestamp=resume_ts)
    )
    assert len(resumed_events) == 7
    assert resumed_events[0].sequence == 4
    assert resumed_events[0].source_timestamp > resume_ts
    assert [e.sequence for e in resumed_events] == [4, 5, 6, 7, 8, 9, 10]
    assert [e.source_timestamp for e in resumed_events] == [
        e.source_timestamp for e in all_events[3:]
    ]


def test_repository_phase1b_parquet_requires_explicit_legacy_contract() -> None:
    path = Path("data/processed/phase1b/metropt3/telemetry.parquet")
    if not path.is_file():
        pytest.skip("Historical Phase 1B telemetry.parquet not present in workspace")
    source = ReplaySource(
        path,
        expected_contract_sha256=PHASE1B_CONTRACT_SHA256,
        expected_source_dataset_sha256=PHASE1B_SOURCE_DATASET_SHA256,
        expected_output_sha256=PHASE1B_PREPARED_OUTPUT_SHA256,
    )
    assert source.identity.contract_sha256 == PHASE1B_CONTRACT_SHA256
