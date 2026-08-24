"""Frozen, extra-forbid Pydantic v2 schemas for runtime scoring and Kafka replay messages."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

HEX_64_PATTERN = r"^[0-9a-f]{64}$"
ERR_SOURCE_TS_NAIVE = "source_timestamp must be timezone-naive"
ERR_EMITTED_AT_UTC = "emitted_at must be timezone-aware UTC"

REPLAY_COMMANDS_TOPIC = "irp.replay.commands.v1"
REPLAY_STATUS_TOPIC = "irp.replay.status.v1"
TELEMETRY_TOPIC = "irp.telemetry.v1"
FEATURES_TOPIC = "irp.features.v1"
SCORES_TOPIC = "irp.scores.v1"
QUARANTINE_TOPIC = "irp.quarantine.v1"
ALERT_EVENTS_TOPIC = "irp.alerts.v1"

AlertAction = Literal["OPENED", "UPDATED", "RESOLVED", "REOPENED"]


class FrozenMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageEvidenceV1(FrozenMessage):
    observations_by_bin: tuple[int, int, int, int, int, int]
    bin_ends: tuple[datetime, datetime, datetime, datetime, datetime, datetime]

    @model_validator(mode="after")
    def validate_coverage(self) -> CoverageEvidenceV1:
        if len(self.observations_by_bin) != 6:
            raise ValueError("observations_by_bin must contain exactly 6 elements")
        if len(self.bin_ends) != 6:
            raise ValueError("bin_ends must contain exactly 6 elements")

        for cnt in self.observations_by_bin:
            if cnt < 24:
                raise ValueError(f"Observation count {cnt} is less than min 24 observations/bin")

        for i in range(len(self.bin_ends) - 1):
            if self.bin_ends[i] >= self.bin_ends[i + 1]:
                raise ValueError("bin_ends must be strictly increasing")
            if self.bin_ends[i].tzinfo is not None:
                raise ValueError("bin_ends must be timezone-naive")

        if self.bin_ends[-1].tzinfo is not None:
            raise ValueError("bin_ends must be timezone-naive")

        return self


class FeatureVectorV1(FrozenMessage):
    schema_version: Literal["feature-vector-v1"] = "feature-vector-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_timestamp: datetime
    emitted_at: datetime
    window_id: UUID
    machine_id: str = Field(min_length=1, max_length=128)
    window_start: datetime
    window_end: datetime
    feature_names: tuple[str, ...] = Field(min_length=1)
    feature_values: tuple[float, ...] = Field(min_length=1)
    coverage: CoverageEvidenceV1

    @model_validator(mode="after")
    def validate_feature_vector(self) -> FeatureVectorV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError(ERR_SOURCE_TS_NAIVE)
        if self.window_start.tzinfo is not None or self.window_end.tzinfo is not None:
            raise ValueError("window_start and window_end must be timezone-naive")
        if self.emitted_at.tzinfo is None:
            raise ValueError(ERR_EMITTED_AT_UTC)

        if not (self.window_start < self.window_end == self.source_timestamp):
            raise ValueError(
                "window_start must be < window_end and window_end must equal source_timestamp"
            )

        if len(self.feature_names) != len(self.feature_values):
            raise ValueError("feature_names and feature_values must have the same length")

        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature_names must contain unique elements")

        for val in self.feature_values:
            if not math.isfinite(val):
                raise ValueError("feature_values must contain only finite numbers")

        return self


class ScoreRequestV1(FrozenMessage):
    model_version: str = Field(min_length=1, max_length=200)
    feature_vector: FeatureVectorV1


class EvidenceValueV1(FrozenMessage):
    feature_name: str
    feature_value: float
    robust_deviation: float

    @model_validator(mode="after")
    def validate_evidence(self) -> EvidenceValueV1:
        if not math.isfinite(self.feature_value) or not math.isfinite(self.robust_deviation):
            raise ValueError("feature_value and robust_deviation must be finite numbers")
        return self


class ScoreDecisionV1(FrozenMessage):
    schema_version: Literal["score-decision-v1"] = "score-decision-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_timestamp: datetime
    emitted_at: datetime
    decision_id: UUID
    window_id: UUID
    model_version: str = Field(min_length=1, max_length=200)
    score: float
    threshold: float
    is_anomaly: bool
    evidence_vector: tuple[EvidenceValueV1, ...]

    @model_validator(mode="after")
    def validate_decision(self) -> ScoreDecisionV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError(ERR_SOURCE_TS_NAIVE)
        if self.emitted_at.tzinfo is None:
            raise ValueError(ERR_EMITTED_AT_UTC)
        if not math.isfinite(self.score) or not math.isfinite(self.threshold):
            raise ValueError("score and threshold must be finite numbers")
        return self


class ApiErrorV1(FrozenMessage):
    code: str
    message: str


class ScoreResponseV1(FrozenMessage):
    success: Literal[True] = True
    data: ScoreDecisionV1
    error: None = None


class ErrorResponseV1(FrozenMessage):
    success: Literal[False] = False
    data: None = None
    error: ApiErrorV1


def _validate_start_command(cmd: ReplayCommandV1) -> None:
    if cmd.range_start is None or cmd.range_end is None:
        raise ValueError("START action requires range_start and range_end")
    if cmd.range_start.tzinfo is not None or cmd.range_end.tzinfo is not None:
        raise ValueError("range_start and range_end must be timezone-naive")
    if cmd.range_start >= cmd.range_end:
        raise ValueError("range_start must be strictly earlier than range_end")
    if cmd.source_timestamp != cmd.range_start:
        raise ValueError("source_timestamp must equal range_start for START action")


def _validate_control_command(cmd: ReplayCommandV1) -> None:
    if cmd.range_start is not None or cmd.range_end is not None:
        raise ValueError(f"{cmd.action} action must not specify range_start or range_end")


class ReplayCommandV1(FrozenMessage):
    schema_version: Literal["replay-command-v1"] = "replay-command-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_timestamp: datetime
    emitted_at: datetime
    command_id: UUID
    action: Literal["START", "PAUSE", "RESUME", "STOP"]
    speed: Literal[1, 100, 1000]
    range_start: datetime | None = None
    range_end: datetime | None = None

    @model_validator(mode="after")
    def validate_command(self) -> ReplayCommandV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError(ERR_SOURCE_TS_NAIVE)
        if self.emitted_at.tzinfo is None:
            raise ValueError(ERR_EMITTED_AT_UTC)

        if self.action == "START":
            _validate_start_command(self)
        else:
            _validate_control_command(self)

        return self


class ReplayStatusV1(FrozenMessage):
    schema_version: Literal["replay-status-v1"] = "replay-status-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_timestamp: datetime
    emitted_at: datetime
    state: Literal["CREATED", "RUNNING", "PAUSED", "STOPPED", "COMPLETED", "FAILED"]
    last_sequence: int | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> ReplayStatusV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError(ERR_SOURCE_TS_NAIVE)
        if self.emitted_at.tzinfo is None:
            raise ValueError(ERR_EMITTED_AT_UTC)

        if self.state in ("STOPPED", "COMPLETED", "FAILED") and (
            self.last_sequence is None or self.last_sequence < 0
        ):
            raise ValueError(f"{self.state} state requires non-negative last_sequence")

        if self.state == "FAILED":
            if not self.error_code:
                raise ValueError("FAILED state requires non-empty error_code")
        else:
            if self.error_code is not None:
                raise ValueError(f"{self.state} state must have error_code=None")

        return self


class TelemetryEventV1(FrozenMessage):
    schema_version: Literal["telemetry-event-v1"] = "telemetry-event-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_timestamp: datetime
    emitted_at: datetime
    machine_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(gt=0)
    tp2: float
    tp3: float
    h1: float
    dv_pressure: float
    reservoirs: float
    oil_temperature: float
    motor_current: float
    comp: Literal[0, 1]
    dv_electric: Literal[0, 1]
    towers: Literal[0, 1]
    mpg: Literal[0, 1]
    lps: Literal[0, 1]
    pressure_switch: Literal[0, 1]
    oil_level: Literal[0, 1]
    caudal_impulses: Literal[0, 1]

    @model_validator(mode="after")
    def validate_telemetry(self) -> TelemetryEventV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError(ERR_SOURCE_TS_NAIVE)
        if self.emitted_at.tzinfo is None:
            raise ValueError(ERR_EMITTED_AT_UTC)

        analog_fields = [
            self.tp2,
            self.tp3,
            self.h1,
            self.dv_pressure,
            self.reservoirs,
            self.oil_temperature,
            self.motor_current,
        ]
        for val in analog_fields:
            if not math.isfinite(val):
                raise ValueError("Analog telemetry values must be finite")

        return self


class QuarantineRecordV1(FrozenMessage):
    schema_version: Literal["quarantine-record-v1"] = "quarantine-record-v1"
    message_id: UUID
    replay_session_id: UUID | None = None
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_timestamp: datetime
    emitted_at: datetime
    original_topic: str = Field(min_length=1, max_length=256)
    partition: int = Field(ge=0)
    offset: int = Field(ge=0)
    payload_sha256: str = Field(pattern=HEX_64_PATTERN)
    error_code: str = Field(min_length=1, max_length=128)
    error_detail: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_quarantine(self) -> QuarantineRecordV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError(ERR_SOURCE_TS_NAIVE)
        if self.emitted_at.tzinfo is None:
            raise ValueError(ERR_EMITTED_AT_UTC)
        return self


class FeatureDeviationV1(FrozenMessage):
    feature_name: str = Field(min_length=1)
    observed_value: float
    baseline_value: float
    absolute_deviation: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_deviation(self) -> FeatureDeviationV1:
        for val in (self.observed_value, self.baseline_value, self.absolute_deviation):
            if not math.isfinite(val):
                raise ValueError("Deviation values must be finite")
        return self


class AlertEventV1(FrozenMessage):
    schema_version: Literal["alert-event-v1"] = "alert-event-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_timestamp: datetime
    emitted_at: datetime
    alert_id: UUID
    machine_id: str = Field(min_length=1)
    action: AlertAction
    first_detection: datetime
    last_detection: datetime
    decision_ids: tuple[UUID, ...] = Field(min_length=1)
    policy_sha256: str = Field(pattern=HEX_64_PATTERN)

    @model_validator(mode="after")
    def validate_alert_event(self) -> AlertEventV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError(ERR_SOURCE_TS_NAIVE)
        if self.emitted_at.tzinfo is None:
            raise ValueError(ERR_EMITTED_AT_UTC)
        if self.first_detection.tzinfo is not None:
            raise ValueError("first_detection must be timezone-naive")
        if self.last_detection.tzinfo is not None:
            raise ValueError("last_detection must be timezone-naive")
        if self.first_detection > self.last_detection:
            raise ValueError("first_detection must not be later than last_detection")
        return self


class EvidenceSnapshotV1(FrozenMessage):
    schema_version: Literal["evidence-snapshot-v1"] = "evidence-snapshot-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_timestamp: datetime
    emitted_at: datetime
    evidence_id: UUID
    alert_id: UUID
    decision_id: UUID
    window_id: UUID
    model_version: str = Field(min_length=1)
    feature_deviations: tuple[FeatureDeviationV1, ...]
    data_quality: dict[str, float | int | str | bool]
    model: dict[str, float | int | str | bool]
    system_health: dict[str, float | int | str | bool]

    @model_validator(mode="after")
    def validate_evidence_snapshot(self) -> EvidenceSnapshotV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError(ERR_SOURCE_TS_NAIVE)
        if self.emitted_at.tzinfo is None:
            raise ValueError(ERR_EMITTED_AT_UTC)
        return self
