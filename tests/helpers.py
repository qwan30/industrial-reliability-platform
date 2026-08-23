"""Deterministic test data shared by Phase 1 tests."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from industrial_reliability.contracts import PHASE1, Event, Phase1Contract, Split


def write_sample_csv(path: Path, timestamps: list[datetime]) -> None:
    """Write synthetic rows with the exact MetroPT source schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(PHASE1.source_columns)
        for index, timestamp in enumerate(timestamps):
            digital = index % 2
            gps_available = index % 2 == 1
            writer.writerow(
                [
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    *(float(index + offset) for offset in range(1, 9)),
                    digital,
                    digital,
                    digital,
                    digital,
                    digital,
                    digital,
                    digital,
                    digital,
                    -8.65934 if gps_available else 0.0,
                    41.2124 if gps_available else 0.0,
                    0.0,
                    1 if gps_available else 0,
                ]
            )


def sample_contract(source: Path) -> Phase1Contract:
    """Return the frozen contract with identity and times adapted to a fixture."""
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader)
        rows = list(reader)
    start = datetime.strptime(rows[0][0], "%Y-%m-%d %H:%M:%S")
    holdout_start = start + timedelta(seconds=4_800)
    events = tuple(
        Event(
            event_id=f"synthetic-{index + 1}",
            failure_type="synthetic",
            source_start=holdout_start + timedelta(seconds=offset),
            source_end=holdout_start + timedelta(seconds=offset + 60),
            source_precision="second",
            paper_count=60,
            local_lps_transition=None,
            disagreement=None,
        )
        for index, offset in enumerate((600, 1_200, 1_800))
    )
    return replace(
        PHASE1,
        dataset_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        dataset_bytes=source.stat().st_size,
        dataset_rows=len(rows),
        dataset_path=str(source),
        train=Split("train", start, start + timedelta(seconds=2_400)),
        calibration=Split(
            "calibration",
            start + timedelta(seconds=2_400),
            holdout_start,
        ),
        holdout=Split("holdout", holdout_start, start + timedelta(seconds=7_200)),
        events=events,
        window_seconds=60,
        window_lookback_seconds=60,
        window_validity_policy="exactly_60_consecutive_one_second_observations",
        stride_seconds=10,
        event_horizon_seconds=120,
    )


def sample_policy(**overrides: Any) -> Phase1Contract:
    """Return the small-window policy used by synthetic tests."""
    defaults = replace(
        PHASE1,
        window_seconds=60,
        window_lookback_seconds=60,
        window_validity_policy="exactly_60_consecutive_one_second_observations",
        stride_seconds=10,
        event_horizon_seconds=120,
    )
    return replace(defaults, **overrides)


def make_segment(seconds: int) -> pd.DataFrame:
    """Build a deterministic, gap-free source-shaped frame."""
    timestamps = pd.date_range("2022-01-01 06:00:00", periods=seconds, freq="s")
    index = np.arange(seconds, dtype=np.float64)
    frame: dict[str, Any] = {"timestamp": timestamps}
    for offset, column in enumerate(PHASE1.analog_columns, start=1):
        frame[column] = index + offset
    for column in ("COMP", "DV_eletric", "Towers", "MPG"):
        frame[column] = (index.astype(np.int64) % 2)
    frame.update(
        {
            "LPS": np.zeros(seconds, dtype=np.int64),
            "Pressure_switch": np.zeros(seconds, dtype=np.int64),
            "Oil_level": np.ones(seconds, dtype=np.int64),
            "Caudal_impulses": index.astype(np.int64) % 2,
            "gpsLong": np.full(seconds, -8.65934),
            "gpsLat": np.full(seconds, 41.2124),
            "gpsSpeed": np.zeros(seconds),
            "gpsQuality": np.ones(seconds, dtype=np.int64),
        }
    )
    return pd.DataFrame(frame, columns=PHASE1.source_columns)


def make_segment_around_split_boundary() -> pd.DataFrame:
    """Build a gap-free frame spanning a synthetic split boundary."""
    frame = make_segment(180)
    frame["timestamp"] = pd.date_range(
        "2022-01-01 06:39:00",
        periods=len(frame),
        freq="s",
    )
    return frame


def sample_contract_for_frame(frame: pd.DataFrame) -> Phase1Contract:
    """Place deterministic train/calibration/holdout splits inside a frame."""
    start = pd.Timestamp(frame["timestamp"].iloc[0]).to_pydatetime()
    end = pd.Timestamp(frame["timestamp"].iloc[-1]).to_pydatetime() + timedelta(seconds=1)
    span = int((end - start).total_seconds())
    train_end = start + timedelta(seconds=span // 3)
    calibration_end = start + timedelta(seconds=2 * span // 3)
    return replace(
        sample_policy(),
        train=Split("train", start, train_end),
        calibration=Split("calibration", train_end, calibration_end),
        holdout=Split("holdout", calibration_end, end),
        events=(),
    )


def seeded_training_matrix(rows: int, columns: int) -> np.ndarray:
    """Return a reproducible, non-degenerate floating-point matrix."""
    return np.random.default_rng(42).normal(size=(rows, columns))


def score_frame(offsets: list[int], scores: list[float]) -> pd.DataFrame:
    """Return scores at caller-supplied second offsets."""
    start = datetime(2022, 1, 1, 6)
    return pd.DataFrame(
        {
            "window_end": [start + timedelta(seconds=offset) for offset in offsets],
            "score": scores,
        }
    )
