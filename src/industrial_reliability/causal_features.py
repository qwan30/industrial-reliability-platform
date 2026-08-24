"""Pure mathematical definitions for causal rolling window statistics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    timestamp: datetime
    analog: tuple[float, ...]
    digital: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CoverageEvidence:
    bin_ends: tuple[datetime, ...]
    observations_by_bin: tuple[int, ...]


ANALOG_STATS = ("last", "mean", "std", "min", "max", "delta")
DIGITAL_STATS = ("last", "active_ratio", "transition_count")


def get_candidate_feature_names(
    analog_columns: tuple[str, ...], digital_columns: tuple[str, ...]
) -> tuple[str, ...]:
    names: list[str] = []
    for col in analog_columns:
        for stat in ANALOG_STATS:
            names.append(f"{col}_{stat}")
    for col in digital_columns:
        for stat in DIGITAL_STATS:
            names.append(f"{col}_{stat}")
    return tuple(names)


def _all_candidate_statistics(
    analog: np.ndarray,
    digital: np.ndarray,
    analog_cols: tuple[str, ...],
    digital_cols: tuple[str, ...],
) -> dict[str, float]:
    stats: dict[str, float] = {}

    # Analog stats (analog shape: (N, num_analog))
    for idx, col in enumerate(analog_cols):
        series = analog[:, idx]
        stats[f"{col}_last"] = float(series[-1])
        stats[f"{col}_mean"] = float(np.mean(series))
        stats[f"{col}_std"] = float(np.std(series, ddof=0))
        stats[f"{col}_min"] = float(np.min(series))
        stats[f"{col}_max"] = float(np.max(series))
        stats[f"{col}_delta"] = float(series[-1] - series[0])

    # Digital stats (digital shape: (N, num_digital))
    for idx, col in enumerate(digital_cols):
        series = digital[:, idx]
        stats[f"{col}_last"] = float(series[-1])
        stats[f"{col}_active_ratio"] = float(np.mean(series == 1))
        transitions = np.count_nonzero(series[1:] != series[:-1]) if len(series) > 1 else 0
        stats[f"{col}_transition_count"] = float(transitions)

    return stats


def compute_feature_values(
    samples: Sequence[TelemetrySample],
    feature_names: Sequence[str],
    analog_cols: tuple[str, ...],
    digital_cols: tuple[str, ...],
) -> tuple[float, ...]:
    if not samples:
        raise ValueError("Cannot compute features on empty samples")
    analog = np.asarray([sample.analog for sample in samples], dtype=np.float64)
    digital = np.asarray([sample.digital for sample in samples], dtype=np.int8)
    all_stats = _all_candidate_statistics(analog, digital, analog_cols, digital_cols)
    return tuple(float(all_stats[name]) for name in feature_names)
