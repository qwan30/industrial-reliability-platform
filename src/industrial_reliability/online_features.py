"""Online streaming feature window aggregator with strict causal parity and fault reset."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from industrial_reliability.causal_features import (
    TelemetrySample,
    compute_feature_values,
)
from industrial_reliability.phase1b_contracts import PHASE1B
from industrial_reliability.phase1b_features import _compute_bin_end
from industrial_reliability.runtime_ids import runtime_id
from industrial_reliability.runtime_messages import (
    CoverageEvidenceV1,
    FeatureVectorV1,
    TelemetryEventV1,
)

SegmentCloseReason = Literal[
    "sequence_gap",
    "conflicting_duplicate",
    "timestamp_regression",
    "invalid_bin",
    "split_boundary",
]

DEFAULT_ANALOG_COLS = (
    "tp2",
    "tp3",
    "h1",
    "dv_pressure",
    "reservoirs",
    "oil_temperature",
    "motor_current",
)
DEFAULT_DIGITAL_COLS = (
    "comp",
    "dv_electric",
    "towers",
    "mpg",
    "lps",
    "pressure_switch",
    "oil_level",
    "caudal_impulses",
)


@dataclass(frozen=True, slots=True)
class BuilderResult:
    features: tuple[FeatureVectorV1, ...]
    segment_closed_reason: SegmentCloseReason | None = None


def _extract_sample(
    event: TelemetryEventV1,
    analog_cols: tuple[str, ...],
    digital_cols: tuple[str, ...],
) -> TelemetrySample:
    analog = tuple(float(getattr(event, col)) for col in analog_cols)
    digital = tuple(int(getattr(event, col)) for col in digital_cols)
    return TelemetrySample(timestamp=event.source_timestamp, analog=analog, digital=digital)


def _hash_event_payload(event: TelemetryEventV1) -> str:
    analog_vals = [
        event.tp2,
        event.tp3,
        event.h1,
        event.dv_pressure,
        event.reservoirs,
        event.oil_temperature,
        event.motor_current,
    ]
    digital_vals = [
        event.comp,
        event.dv_electric,
        event.towers,
        event.mpg,
        event.lps,
        event.pressure_switch,
        event.oil_level,
        event.caudal_impulses,
    ]
    raw = f"{event.sequence}:{event.source_timestamp.isoformat()}:{analog_vals}:{digital_vals}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class OnlineFeatureBuilder:
    def __init__(
        self,
        replay_session_id: UUID,
        machine_id: str,
        source_dataset_sha256: str,
        contract_sha256: str,
        feature_names: tuple[str, ...],
        clock: Callable[[], datetime] | None = None,
        stride_seconds: int = 300,
        lookback_bins: int = 6,
        min_bin_observations: int = 24,
        analog_cols: tuple[str, ...] = DEFAULT_ANALOG_COLS,
        digital_cols: tuple[str, ...] | None = None,
    ) -> None:
        self.replay_session_id = replay_session_id
        self.machine_id = machine_id
        self.source_dataset_sha256 = source_dataset_sha256
        self.contract_sha256 = contract_sha256
        self.feature_names = feature_names
        self.clock = clock or (lambda: datetime.now(UTC))
        self.stride_seconds = stride_seconds
        self.lookback_bins = lookback_bins
        self.min_bin_observations = min_bin_observations
        self.analog_cols = analog_cols
        if digital_cols is None:
            self.digital_cols = tuple(
                c for c in PHASE1B.digital_columns if c in PHASE1B.predictor_columns
            )
        else:
            self.digital_cols = digital_cols

        self._last_sequence: int | None = None
        self._last_timestamp: datetime | None = None
        self._last_event_id: UUID | None = None
        self._last_payload_hash: str | None = None

        self._current_bin_end: datetime | None = None
        self._current_bin_samples: list[TelemetrySample] = []
        self._valid_bin_buffer: list[tuple[datetime, list[TelemetrySample]]] = []
        self._is_complete: bool = False

    @property
    def is_complete(self) -> bool:
        return self._is_complete

    def _reset_segment(self) -> None:
        self._current_bin_end = None
        self._current_bin_samples.clear()
        self._valid_bin_buffer.clear()

    def _emit_window(self, buffer: list[tuple[datetime, list[TelemetrySample]]]) -> FeatureVectorV1:
        window_end = buffer[-1][0]
        window_start = buffer[0][0] - timedelta(seconds=self.stride_seconds)
        bin_ends = tuple(b[0] for b in buffer)
        counts = tuple(len(b[1]) for b in buffer)
        coverage = CoverageEvidenceV1(
            bin_ends=bin_ends,  # type: ignore[arg-type]
            observations_by_bin=counts,  # type: ignore[arg-type]
        )

        all_samples: list[TelemetrySample] = []
        for _, samples in buffer:
            all_samples.extend(samples)

        feature_values = compute_feature_values(
            all_samples, self.feature_names, self.analog_cols, self.digital_cols
        )
        window_id = runtime_id(
            "window",
            self.replay_session_id,
            window_end.isoformat(timespec="seconds"),
        )

        return FeatureVectorV1(
            message_id=window_id,
            window_id=window_id,
            replay_session_id=self.replay_session_id,
            source_dataset_sha256=self.source_dataset_sha256,
            contract_sha256=self.contract_sha256,
            source_timestamp=window_end,
            emitted_at=self.clock(),
            machine_id=self.machine_id,
            window_start=window_start,
            window_end=window_end,
            feature_names=self.feature_names,
            feature_values=feature_values,
            coverage=coverage,
        )

    def _finalize_current_bin(self) -> list[FeatureVectorV1]:
        emitted: list[FeatureVectorV1] = []
        if self._current_bin_end is None:
            return emitted

        if len(self._current_bin_samples) >= self.min_bin_observations:
            if self._valid_bin_buffer:
                prev_end = self._valid_bin_buffer[-1][0]
                delta = (self._current_bin_end - prev_end).total_seconds()
                if delta != self.stride_seconds:
                    self._valid_bin_buffer.clear()

            self._valid_bin_buffer.append((self._current_bin_end, list(self._current_bin_samples)))
            if len(self._valid_bin_buffer) > self.lookback_bins:
                self._valid_bin_buffer.pop(0)

            if len(self._valid_bin_buffer) == self.lookback_bins:
                emitted.append(self._emit_window(self._valid_bin_buffer))
        else:
            self._valid_bin_buffer.clear()

        self._current_bin_samples.clear()
        return emitted

    def _check_sequence_and_ordering(
        self, event: TelemetryEventV1, payload_hash: str
    ) -> tuple[bool, SegmentCloseReason | None]:
        """Returns (should_ignore, close_reason)."""
        if self._last_sequence is not None and event.sequence == self._last_sequence:
            if event.message_id == self._last_event_id and payload_hash == self._last_payload_hash:
                return True, None
            self._reset_segment()
            return True, "conflicting_duplicate"

        close_reason: SegmentCloseReason | None = None
        if self._last_sequence is not None and event.sequence != self._last_sequence + 1:
            self._reset_segment()
            close_reason = "sequence_gap"
        elif self._last_timestamp is not None and event.source_timestamp < self._last_timestamp:
            self._reset_segment()
            close_reason = "timestamp_regression"

        return False, close_reason

    def push(self, event: TelemetryEventV1) -> BuilderResult:
        payload_hash = _hash_event_payload(event)

        should_ignore, close_reason = self._check_sequence_and_ordering(event, payload_hash)
        if should_ignore:
            return BuilderResult(features=(), segment_closed_reason=close_reason)

        # 3. Bin boundary checks
        event_bin_end = _compute_bin_end(event.source_timestamp)
        emitted_features: list[FeatureVectorV1] = []

        if self._current_bin_end is None:
            self._current_bin_end = event_bin_end
        elif event_bin_end != self._current_bin_end:
            if event_bin_end < self._current_bin_end:
                self._reset_segment()
                close_reason = "timestamp_regression"
                self._current_bin_end = event_bin_end
            else:
                delta = (event_bin_end - self._current_bin_end).total_seconds()
                if delta > self.stride_seconds:
                    self._finalize_current_bin()
                    self._valid_bin_buffer.clear()
                    self._current_bin_end = event_bin_end
                    close_reason = "invalid_bin"
                else:
                    emitted_features.extend(self._finalize_current_bin())
                    self._current_bin_end = event_bin_end

        sample = _extract_sample(event, self.analog_cols, self.digital_cols)
        self._current_bin_samples.append(sample)

        self._last_sequence = event.sequence
        self._last_timestamp = event.source_timestamp
        self._last_event_id = event.message_id
        self._last_payload_hash = payload_hash

        return BuilderResult(
            features=tuple(emitted_features),
            segment_closed_reason=close_reason,
        )

    def complete(self, source_timestamp: datetime) -> BuilderResult:
        if self._last_timestamp is not None and source_timestamp < self._last_timestamp:
            raise ValueError("completion timestamp cannot precede last received telemetry")

        emitted = self._finalize_current_bin()
        self._is_complete = True
        return BuilderResult(features=tuple(emitted), segment_closed_reason=None)
