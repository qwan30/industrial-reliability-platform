"""Immutable, executable constants for the Phase 1 benchmark."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import cast


@dataclass(frozen=True)
class Split:
    name: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Event:
    event_id: str
    failure_type: str
    source_start: datetime
    source_end: datetime
    source_precision: str
    paper_count: int
    local_lps_transition: datetime | None
    disagreement: str | None


@dataclass(frozen=True)
class Phase1Contract:
    contract_version: str
    approval_provenance: str
    dataset_license_status: str
    dataset_sha256: str
    dataset_bytes: int
    dataset_rows: int
    source_columns: tuple[str, ...]
    predictor_columns: tuple[str, ...]
    analog_columns: tuple[str, ...]
    digital_columns: tuple[str, ...]
    analog_statistics: tuple[str, ...]
    digital_statistics: tuple[str, ...]
    analog_std_ddof: int
    feature_columns: tuple[str, ...]
    train: Split
    calibration: Split
    holdout: Split
    events: tuple[Event, ...]
    window_seconds: int = 1800
    stride_seconds: int = 300
    event_horizon_seconds: int = 7200
    threshold_quantile: float = 0.995
    threshold_method: str = "higher"
    min_detected_events: int = 2
    max_false_episodes_per_day: float = 1.0
    max_time_in_alert: float = 0.05
    random_seed: int = 42
    benchmark_policy_version: str = "phase1-policy-v1"
    robust_mad_scale: float = 1.4826
    statistical_aggregation: str = "max_abs_robust_z"
    anomaly_inclusive: bool = True
    segment_anchor_policy: str = "first_complete_window_then_segment_relative_stride"
    isolation_forest_estimators: int = 200
    isolation_forest_max_samples: str = "auto"
    isolation_forest_contamination: str = "auto"
    isolation_forest_n_jobs: int = 1
    isolation_forest_score_rule: str = "negative_score_samples"
    autoencoder_hidden_width: int = 64
    autoencoder_bottleneck_width: int = 16
    autoencoder_activation: str = "relu"
    autoencoder_loss: str = "mse"
    autoencoder_optimizer: str = "adam"
    autoencoder_learning_rate: float = 0.001
    autoencoder_batch_size: int = 256
    autoencoder_epochs: int = 20
    autoencoder_scaler: str = "standard_scaler_train_only"
    autoencoder_device: str = "cpu"
    autoencoder_deterministic: bool = True
    autoencoder_num_workers: int = 0
    episode_interval_policy: str = "first_window_end_to_last_window_end_plus_stride"
    event_label_policy: str = "window_end_in_prewarning_horizon_or_episode_overlap"
    normal_exposure_policy: str = "normal_valid_decisions_times_stride"


SOURCE_COLUMNS = (
    "timestamp",
    "TP2",
    "TP3",
    "H1",
    "DV_pressure",
    "Reservoirs",
    "Oil_temperature",
    "Flowmeter",
    "Motor_current",
    "COMP",
    "DV_eletric",
    "Towers",
    "MPG",
    "LPS",
    "Pressure_switch",
    "Oil_level",
    "Caudal_impulses",
    "gpsLong",
    "gpsLat",
    "gpsSpeed",
    "gpsQuality",
)
ANALOG_COLUMNS = (
    "TP2",
    "TP3",
    "H1",
    "DV_pressure",
    "Reservoirs",
    "Oil_temperature",
    "Flowmeter",
    "Motor_current",
)
DIGITAL_COLUMNS = ("COMP", "DV_eletric", "Towers", "MPG", "Caudal_impulses")
ANALOG_STATISTICS = ("last", "mean", "std", "min", "max", "delta")
DIGITAL_STATISTICS = ("last", "active_ratio", "transition_count")
PREDICTOR_COLUMNS = ANALOG_COLUMNS + DIGITAL_COLUMNS
FEATURE_COLUMNS = tuple(
    f"{column}__{statistic}"
    for column in ANALOG_COLUMNS
    for statistic in ANALOG_STATISTICS
) + tuple(
    f"{column}__{statistic}"
    for column in DIGITAL_COLUMNS
    for statistic in DIGITAL_STATISTICS
)


PHASE1 = Phase1Contract(
    contract_version="phase1-v1",
    approval_provenance=(
        "user's 2026-08-24 instruction to commit/push the research, plan phase by phase, "
        "then execute continuously"
    ),
    dataset_license_status=(
        "approved for private feasibility analysis only; official-release equivalence and "
        "license remain explicitly unknown"
    ),
    dataset_sha256="3fd0788c1b8fb7753ac0a2047f487c87f59b8b36af2f5553e4990354ed86d168",
    dataset_bytes=1_646_201_046,
    dataset_rows=10_773_588,
    source_columns=SOURCE_COLUMNS,
    predictor_columns=PREDICTOR_COLUMNS,
    analog_columns=ANALOG_COLUMNS,
    digital_columns=DIGITAL_COLUMNS,
    analog_statistics=ANALOG_STATISTICS,
    digital_statistics=DIGITAL_STATISTICS,
    analog_std_ddof=0,
    feature_columns=FEATURE_COLUMNS,
    train=Split("train", datetime(2022, 1, 1, 6), datetime(2022, 2, 1)),
    calibration=Split("calibration", datetime(2022, 2, 1), datetime(2022, 2, 21)),
    holdout=Split("holdout", datetime(2022, 2, 21), datetime(2022, 6, 2, 15, 49, 54)),
    events=(
        Event(
            event_id="failure-1",
            failure_type="clients air leak",
            source_start=datetime(2022, 2, 28, 21, 53),
            source_end=datetime(2022, 3, 1, 2),
            source_precision="minute",
            paper_count=14_820,
            local_lps_transition=datetime(2022, 2, 28, 22, 50, 43),
            disagreement="paper time is minute-level, not exact :00 activation",
        ),
        Event(
            event_id="failure-2",
            failure_type="air-dryer leak",
            source_start=datetime(2022, 3, 23, 14, 54),
            source_end=datetime(2022, 3, 23, 15, 24),
            source_precision="minute",
            paper_count=1_800,
            local_lps_transition=None,
            disagreement="2022 narrative conflicts with 2026 table and local interval",
        ),
        Event(
            event_id="failure-3",
            failure_type="compressor oil leak",
            source_start=datetime(2022, 5, 30, 12),
            source_end=datetime(2022, 6, 2, 6, 18),
            source_precision="minute",
            paper_count=281_800,
            local_lps_transition=datetime(2022, 6, 2, 6, 18, 33),
            disagreement=(
                "paper count exceeds its stated gap-free interval and local coverage has "
                "43,197 absent seconds"
            ),
        ),
    ),
)


def _serialize(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    return value


def contract_manifest(contract: Phase1Contract) -> dict[str, object]:
    manifest_without_hash = cast(dict[str, object], _serialize(asdict(contract)))
    payload = json.dumps(
        manifest_without_hash,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **manifest_without_hash,
        "contract_sha256": hashlib.sha256(payload).hexdigest(),
    }
