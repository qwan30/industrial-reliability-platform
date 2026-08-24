"""Immutable, executable constants and contracts for the Phase 1B MetroPT-3 validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import cast

from industrial_reliability.contracts import Event, Split


@dataclass(frozen=True, slots=True)
class MetroPT3Event:
    event_id: str
    source_start_minute: datetime
    source_end_minute: datetime
    condition: str

    @property
    def normalized_end(self) -> datetime:
        return self.source_end_minute + timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class Phase1BContract:
    contract_version: str
    source_url: str
    source_doi: str
    license: str
    archive_sha256: str
    csv_member: str
    expected_rows: int
    source_columns: tuple[str, ...]
    canonical_columns: tuple[str, ...]
    analog_columns: tuple[str, ...]
    digital_columns: tuple[str, ...]
    predictor_columns: tuple[str, ...]
    train: Split
    calibration: Split
    holdout: Split
    events: tuple[MetroPT3Event, ...]
    bin_seconds: int = 300
    min_bin_observations: int = 24
    lookback_bins: int = 6
    stride_seconds: int = 300
    event_horizon_seconds: int = 7_200
    threshold_quantile: float = 0.995
    threshold_method: str = "higher"
    anomaly_inclusive: bool = True
    min_detected_events: int = 3
    max_false_episodes_per_day: float = 1.0
    max_time_in_alert: float = 0.05
    random_seed: int = 42
    robust_mad_scale: float = 1.4826
    isolation_forest_estimators: int = 200
    isolation_forest_max_samples: str = "auto"
    isolation_forest_contamination: str = "auto"
    isolation_forest_n_jobs: int = 1
    autoencoder_hidden_width: int = 64
    autoencoder_bottleneck_width: int = 16
    autoencoder_learning_rate: float = 0.001
    autoencoder_batch_size: int = 256
    autoencoder_epochs: int = 20


PHASE1B = Phase1BContract(
    contract_version="phase1b-contract-v1",
    source_url="https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip",
    source_doi="10.24432/C5VW3R",
    license="CC BY 4.0",
    archive_sha256="aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a",
    csv_member="MetroPT3(AirCompressor).csv",
    expected_rows=1_516_948,
    source_columns=(
        "Unnamed: 0",
        "timestamp",
        "TP2",
        "TP3",
        "H1",
        "DV_pressure",
        "Reservoirs",
        "Oil_temperature",
        "Motor_current",
        "COMP",
        "DV_eletric",
        "Towers",
        "MPG",
        "LPS",
        "Pressure_switch",
        "Oil_level",
        "Caudal_impulses",
    ),
    canonical_columns=(
        "timestamp",
        "tp2",
        "tp3",
        "h1",
        "dv_pressure",
        "reservoirs",
        "oil_temperature",
        "motor_current",
        "comp",
        "dv_electric",
        "towers",
        "mpg",
        "lps",
        "pressure_switch",
        "oil_level",
        "caudal_impulses",
    ),
    analog_columns=(
        "tp2",
        "tp3",
        "h1",
        "dv_pressure",
        "reservoirs",
        "oil_temperature",
        "motor_current",
    ),
    digital_columns=(
        "comp",
        "dv_electric",
        "towers",
        "mpg",
        "pressure_switch",
        "oil_level",
        "caudal_impulses",
        "lps",
    ),
    predictor_columns=(
        "tp2",
        "tp3",
        "h1",
        "dv_pressure",
        "reservoirs",
        "oil_temperature",
        "motor_current",
        "comp",
        "dv_electric",
        "towers",
        "mpg",
        "pressure_switch",
        "oil_level",
        "caudal_impulses",
    ),
    train=Split(
        name="train",
        start=datetime(2020, 2, 1, 0, 0),
        end=datetime(2020, 2, 22, 0, 0),
    ),
    calibration=Split(
        name="calibration",
        start=datetime(2020, 2, 22, 0, 0),
        end=datetime(2020, 3, 1, 0, 0),
    ),
    holdout=Split(
        name="holdout",
        start=datetime(2020, 3, 1, 0, 0),
        end=datetime(2020, 9, 1, 4, 0),
    ),
    events=(
        MetroPT3Event(
            event_id="metropt3-1",
            source_start_minute=datetime(2020, 4, 18, 0, 0),
            source_end_minute=datetime(2020, 4, 18, 23, 59),
            condition="air leak / high stress",
        ),
        MetroPT3Event(
            event_id="metropt3-2",
            source_start_minute=datetime(2020, 5, 29, 23, 30),
            source_end_minute=datetime(2020, 5, 30, 6, 0),
            condition="air leak / high stress",
        ),
        MetroPT3Event(
            event_id="metropt3-3",
            source_start_minute=datetime(2020, 6, 5, 10, 0),
            source_end_minute=datetime(2020, 6, 7, 14, 30),
            condition="air leak / high stress",
        ),
        MetroPT3Event(
            event_id="metropt3-4",
            source_start_minute=datetime(2020, 7, 15, 14, 30),
            source_end_minute=datetime(2020, 7, 15, 19, 0),
            condition="air leak / high stress",
        ),
    ),
)


def phase1b_evaluation_events() -> tuple[Event, ...]:
    return tuple(
        Event(
            event_id=item.event_id,
            failure_type=item.condition,
            source_start=item.source_start_minute,
            source_end=item.normalized_end,
            source_precision="minute",
            paper_count=0,
            local_lps_transition=None,
            disagreement=None,
        )
        for item in PHASE1B.events
    )


def _serialize(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def phase1b_contract_manifest() -> dict[str, object]:
    manifest_without_hash = cast(dict[str, object], _serialize(asdict(PHASE1B)))
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
