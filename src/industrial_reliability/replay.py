"""Deterministic telemetry replay source and session controller."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pyarrow.compute as pc
import pyarrow.parquet as pq

from industrial_reliability.artifact_integrity import (
    PreparedArtifactIdentity,
    verify_prepared_parquet,
)
from industrial_reliability.runtime_ids import runtime_id
from industrial_reliability.runtime_messages import (
    ReplayCommandV1,
    ReplayStatusV1,
    TelemetryEventV1,
)


class ReplayContractError(ValueError):
    """Raised when replay ordering, timestamp, or state transition constraints are violated."""


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"START"}),
    "RUNNING": frozenset({"PAUSE", "STOP"}),
    "PAUSED": frozenset({"RESUME", "STOP"}),
    "STOPPED": frozenset(),
    "COMPLETED": frozenset(),
    "FAILED": frozenset(),
}


def pace_seconds(previous: datetime, current: datetime, speed: int) -> float:
    if speed not in (1, 100, 1000) or current <= previous:
        raise ReplayContractError("invalid speed or non-increasing source time")
    return (current - previous).total_seconds() / speed


@dataclass(frozen=True, slots=True)
class ReplayController:
    session_id: UUID
    source_dataset_sha256: str
    contract_sha256: str
    state: str = "CREATED"
    speed: int = 1
    range_start: datetime | None = None
    range_end: datetime | None = None
    current_source_timestamp: datetime | None = None
    last_sequence: int | None = None
    error_code: str | None = None

    @classmethod
    def created(
        cls, session_id: UUID, dataset_sha256: str, contract_sha256: str
    ) -> ReplayController:
        return cls(
            session_id=session_id,
            source_dataset_sha256=dataset_sha256,
            contract_sha256=contract_sha256,
            state="CREATED",
        )

    def apply(self, command: ReplayCommandV1) -> ReplayController:
        if command.replay_session_id != self.session_id:
            raise ReplayContractError("Command replay_session_id does not match controller session")

        allowed = ALLOWED_TRANSITIONS.get(self.state, frozenset())
        if command.action not in allowed:
            raise ReplayContractError(
                f"Transition {command.action} is not allowed from state {self.state}"
            )

        if command.action == "START":
            return ReplayController(
                session_id=self.session_id,
                source_dataset_sha256=command.source_dataset_sha256,
                contract_sha256=command.contract_sha256,
                state="RUNNING",
                speed=command.speed,
                range_start=command.range_start,
                range_end=command.range_end,
                current_source_timestamp=command.source_timestamp,
                last_sequence=0,
                error_code=None,
            )
        if command.action == "PAUSE":
            return ReplayController(
                session_id=self.session_id,
                source_dataset_sha256=self.source_dataset_sha256,
                contract_sha256=self.contract_sha256,
                state="PAUSED",
                speed=self.speed,
                range_start=self.range_start,
                range_end=self.range_end,
                current_source_timestamp=command.source_timestamp,
                last_sequence=self.last_sequence,
                error_code=None,
            )
        if command.action == "RESUME":
            return ReplayController(
                session_id=self.session_id,
                source_dataset_sha256=self.source_dataset_sha256,
                contract_sha256=self.contract_sha256,
                state="RUNNING",
                speed=command.speed,
                range_start=self.range_start,
                range_end=self.range_end,
                current_source_timestamp=command.source_timestamp,
                last_sequence=self.last_sequence,
                error_code=None,
            )
        if command.action == "STOP":
            return ReplayController(
                session_id=self.session_id,
                source_dataset_sha256=self.source_dataset_sha256,
                contract_sha256=self.contract_sha256,
                state="STOPPED",
                speed=self.speed,
                range_start=self.range_start,
                range_end=self.range_end,
                current_source_timestamp=command.source_timestamp,
                last_sequence=self.last_sequence or 0,
                error_code=None,
            )

        raise ReplayContractError(f"Unknown action: {command.action}")

    def mark_completed(self, last_sequence: int, source_timestamp: datetime) -> ReplayController:
        return ReplayController(
            session_id=self.session_id,
            source_dataset_sha256=self.source_dataset_sha256,
            contract_sha256=self.contract_sha256,
            state="COMPLETED",
            speed=self.speed,
            range_start=self.range_start,
            range_end=self.range_end,
            current_source_timestamp=source_timestamp,
            last_sequence=last_sequence,
            error_code=None,
        )

    def mark_failed(
        self, error_code: str, last_sequence: int, source_timestamp: datetime
    ) -> ReplayController:
        return ReplayController(
            session_id=self.session_id,
            source_dataset_sha256=self.source_dataset_sha256,
            contract_sha256=self.contract_sha256,
            state="FAILED",
            speed=self.speed,
            range_start=self.range_start,
            range_end=self.range_end,
            current_source_timestamp=source_timestamp,
            last_sequence=last_sequence,
            error_code=error_code,
        )

    def status(self, emitted_at: datetime | None = None) -> ReplayStatusV1:
        emitted = emitted_at if emitted_at is not None else datetime.now(UTC)
        source_ts = self.current_source_timestamp or self.range_start or datetime(2020, 1, 1)
        message_id = runtime_id("status", self.session_id, f"{self.state}:{self.last_sequence}")
        return ReplayStatusV1(
            message_id=message_id,
            replay_session_id=self.session_id,
            source_dataset_sha256=self.source_dataset_sha256,
            contract_sha256=self.contract_sha256,
            source_timestamp=source_ts,
            emitted_at=emitted,
            state=self.state,  # type: ignore[arg-type]
            last_sequence=self.last_sequence,
            error_code=self.error_code,
        )


class ReplaySource:
    def __init__(
        self,
        parquet_path: Path,
        *,
        expected_contract_sha256: str,
        expected_source_dataset_sha256: str,
        expected_output_sha256: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = parquet_path.resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Parquet source not found: {self.path}")
        self.identity: PreparedArtifactIdentity = verify_prepared_parquet(
            self.path,
            expected_contract_sha256=expected_contract_sha256,
            expected_source_dataset_sha256=expected_source_dataset_sha256,
            expected_output_sha256=expected_output_sha256,
        )
        self.clock = clock if clock is not None else (lambda: datetime.now(UTC))


    def iter_events(
        self,
        command: ReplayCommandV1,
        start_sequence: int = 1,
        resume_from_timestamp: datetime | None = None,
    ) -> Iterator[TelemetryEventV1]:
        if command.range_start is None or command.range_end is None:
            raise ReplayContractError("ReplayCommand must specify range_start and range_end")

        table = pq.read_table(self.path)
        ts_col = table["timestamp"]

        import pyarrow as pa

        lower_bound = (
            resume_from_timestamp if resume_from_timestamp is not None else command.range_start
        )
        lower_scalar = pa.scalar(lower_bound, type=ts_col.type)
        upper_scalar = pa.scalar(command.range_end, type=ts_col.type)
        lower_op = pc.greater if resume_from_timestamp is not None else pc.greater_equal
        mask = pc.and_(
            lower_op(ts_col, lower_scalar),
            pc.less(ts_col, upper_scalar),
        )
        filtered = table.filter(mask)
        df = filtered.to_pandas()

        if df.empty:
            return

        # Validate strictly increasing timestamps
        timestamps = df["timestamp"].tolist()
        for i in range(len(timestamps) - 1):
            if timestamps[i] >= timestamps[i + 1]:
                raise ReplayContractError(
                    f"Non-increasing timestamp detected at index {i}: {timestamps[i]} >= {timestamps[i + 1]}"
                )

        seq = start_sequence
        for row in df.itertuples(index=False):
            ts = (
                row.timestamp.to_pydatetime()
                if hasattr(row.timestamp, "to_pydatetime")
                else row.timestamp
            )
            msg_id = runtime_id("telemetry", command.replay_session_id, str(seq))
            yield TelemetryEventV1(
                message_id=msg_id,
                replay_session_id=command.replay_session_id,
                source_dataset_sha256=self.identity.source_dataset_sha256,
                contract_sha256=self.identity.contract_sha256,
                source_timestamp=ts,
                emitted_at=self.clock(),
                machine_id="metropt-compressor-01",
                sequence=seq,
                tp2=float(row.tp2),
                tp3=float(row.tp3),
                h1=float(row.h1),
                dv_pressure=float(row.dv_pressure),
                reservoirs=float(row.reservoirs),
                oil_temperature=float(row.oil_temperature),
                motor_current=float(row.motor_current),
                comp=int(row.comp),  # type: ignore[arg-type]
                dv_electric=int(row.dv_electric),  # type: ignore[arg-type]
                towers=int(row.towers),  # type: ignore[arg-type]
                mpg=int(row.mpg),  # type: ignore[arg-type]
                lps=int(row.lps),  # type: ignore[arg-type]
                pressure_switch=int(row.pressure_switch),  # type: ignore[arg-type]
                oil_level=int(row.oil_level),  # type: ignore[arg-type]
                caudal_impulses=int(row.caudal_impulses),  # type: ignore[arg-type]
            )
            seq += 1
