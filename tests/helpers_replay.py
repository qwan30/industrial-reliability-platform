"""Test fixture helpers for Phase 3 Kafka replay and telemetry contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from industrial_reliability.runtime_messages import (
    QuarantineRecordV1,
    ReplayCommandV1,
    ReplayStatusV1,
    TelemetryEventV1,
)


def make_sample_telemetry_event(
    sequence: int = 1,
    session_id: UUID | None = None,
    source_timestamp: datetime | None = None,
    machine_id: str = "compressor-01",
) -> TelemetryEventV1:
    return TelemetryEventV1(
        message_id=uuid4(),
        replay_session_id=session_id or uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=source_timestamp or datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        machine_id=machine_id,
        sequence=sequence,
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


def make_sample_replay_command(
    action: str = "START",
    session_id: UUID | None = None,
    speed: int = 1000,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
) -> ReplayCommandV1:
    r_start = range_start or datetime(2020, 3, 1, 0, 0, 0)
    r_end = range_end or datetime(2020, 3, 1, 0, 1, 0)
    return ReplayCommandV1(
        message_id=uuid4(),
        replay_session_id=session_id or uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=r_start,
        emitted_at=datetime.now(UTC),
        command_id=uuid4(),
        action=action,  # type: ignore[arg-type]
        speed=speed,  # type: ignore[arg-type]
        range_start=r_start if action == "START" else None,
        range_end=r_end if action == "START" else None,
    )


def make_sample_replay_status(
    state: str = "RUNNING",
    session_id: UUID | None = None,
    last_sequence: int | None = 1,
    error_code: str | None = None,
) -> ReplayStatusV1:
    return ReplayStatusV1(
        message_id=uuid4(),
        replay_session_id=session_id or uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        state=state,  # type: ignore[arg-type]
        last_sequence=last_sequence,
        error_code=error_code,
    )


def make_sample_quarantine(
    error_code: str = "INVALID_PAYLOAD",
    topic: str = "irp.replay.commands.v1",
) -> QuarantineRecordV1:
    return QuarantineRecordV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        original_topic=topic,
        partition=0,
        offset=42,
        payload_sha256="c" * 64,
        error_code=error_code,
        error_detail="Invalid data format",
    )
