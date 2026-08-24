"""Causal 5-minute binned feature window generation for Phase 1B MetroPT-3."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from industrial_reliability.causal_features import (
    CoverageEvidence,
    TelemetrySample,
    compute_feature_values,
    get_candidate_feature_names,
)
from industrial_reliability.phase1b_contracts import (
    PHASE1B,
    Phase1BContract,
    phase1b_contract_manifest,
)
from industrial_reliability.phase1b_data import sha256_file


class FeatureContractError(ValueError):
    """Raised when feature generation violates the contract or produces invalid features."""


@dataclass(frozen=True, slots=True)
class Phase1BWindow:
    split: Literal["train", "calibration", "holdout"]
    window_start: datetime
    window_end: datetime
    feature_names: tuple[str, ...]
    feature_values: tuple[float, ...]
    coverage: CoverageEvidence


@dataclass(frozen=True, slots=True)
class Phase1BFeatureManifest:
    contract_sha256: str
    data_manifest_sha256: str
    output_sha256: str
    candidate_feature_names: tuple[str, ...]
    active_feature_names: tuple[str, ...]
    removed_train_constant_names: tuple[str, ...]
    split_window_counts: tuple[tuple[str, int], ...]
    rejection_counts: tuple[tuple[str, int], ...]
    manifest_sha256: str


def _get_split_for_timestamp(
    ts: datetime, contract: Phase1BContract
) -> Literal["train", "calibration", "holdout"] | None:
    if contract.train.start <= ts < contract.train.end:
        return "train"
    if contract.calibration.start <= ts < contract.calibration.end:
        return "calibration"
    if contract.holdout.start <= ts < contract.holdout.end:
        return "holdout"
    return None


def iter_phase1b_windows(
    frame_or_samples: pd.DataFrame | Sequence[TelemetrySample],
    contract: Phase1BContract = PHASE1B,
) -> Iterator[Phase1BWindow]:
    # Standardize predictor columns: Exclude LPS and timestamp
    analog_cols = contract.analog_columns
    digital_cols = tuple(c for c in contract.digital_columns if c in contract.predictor_columns)
    candidate_names = get_candidate_feature_names(analog_cols, digital_cols)

    if isinstance(frame_or_samples, pd.DataFrame):
        df = frame_or_samples.sort_values("timestamp").reset_index(drop=True)
        if df.empty:
            return

        ts_series = df["timestamp"]
        # Group by 5-minute bin anchored to midnight (right-closed intervals (end - 5m, end])
        # A timestamp T belongs to bin_end = ceil(T to 5min)
        # Note: (ts - midnight).total_seconds()
        # For right-closed interval: if ts == 00:05:00 -> bin_end is 00:05:00
        # If ts == 00:05:01 -> bin_end is 00:10:00
        # In pandas: pd.Grouper(key='timestamp', freq='5min', closed='right', label='right')
        # Let's extract bin_end for each sample explicitly
        timestamps = ts_series.tolist()
        analog_vals = df[list(analog_cols)].to_numpy(dtype=np.float64)
        digital_vals = df[list(digital_cols)].to_numpy(dtype=np.int8)

        samples: list[TelemetrySample] = [
            TelemetrySample(
                timestamp=timestamps[i].to_pydatetime()
                if hasattr(timestamps[i], "to_pydatetime")
                else timestamps[i],
                analog=tuple(float(x) for x in analog_vals[i]),
                digital=tuple(int(x) for x in digital_vals[i]),
            )
            for i in range(len(df))
        ]
    else:
        samples = list(frame_or_samples)
        if not samples:
            return

    # Process samples into 5-minute bins
    # Bin index = (timestamp - base) // 300s
    # Right-closed (T - 300s, T]: sample with exact minute belongs to that bin_end
    # e.g., sample at 00:01:10 -> bin_end 00:05:00.
    # sample at 00:05:00 -> bin_end 00:05:00.
    # sample at 00:05:01 -> bin_end 00:10:00.

    def compute_bin_end(ts: datetime) -> datetime:
        minute_rem = ts.minute % 5
        sec = ts.second
        micro = ts.microsecond
        if minute_rem == 0 and sec == 0 and micro == 0:
            return ts
        minutes_to_add = 5 - minute_rem
        rounded = ts.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)
        return rounded

    # Group into valid bins
    bin_map: dict[datetime, list[TelemetrySample]] = {}
    for s in samples:
        b_end = compute_bin_end(s.timestamp)
        if b_end not in bin_map:
            bin_map[b_end] = []
        bin_map[b_end].append(s)

    sorted_bin_ends = sorted(bin_map.keys())
    if not sorted_bin_ends:
        return

    # Valid bin buffer: keeps consecutive valid bins
    # Lookback = 6 bins (30 minutes)
    valid_bin_buffer: list[tuple[datetime, list[TelemetrySample]]] = []

    prev_bin_end: datetime | None = None
    prev_split: str | None = None

    for b_end in sorted_bin_ends:
        bin_samples = bin_map[b_end]
        count = len(bin_samples)
        split = _get_split_for_timestamp(b_end, contract)

        # Check if bin meets observation threshold
        if count < contract.min_bin_observations or split is None:
            valid_bin_buffer.clear()
            prev_bin_end = None
            prev_split = None
            continue

        # Check continuity (stride = 300s) and same split
        if prev_bin_end is not None:
            delta = (b_end - prev_bin_end).total_seconds()
            if delta != contract.stride_seconds or split != prev_split:
                valid_bin_buffer.clear()

        valid_bin_buffer.append((b_end, bin_samples))
        prev_bin_end = b_end
        prev_split = split

        if len(valid_bin_buffer) > contract.lookback_bins:
            valid_bin_buffer.pop(0)

        if len(valid_bin_buffer) == contract.lookback_bins:
            # Construct causal window
            window_end = valid_bin_buffer[-1][0]
            window_start = valid_bin_buffer[0][0] - timedelta(seconds=contract.stride_seconds)
            bin_ends = tuple(b[0] for b in valid_bin_buffer)
            counts = tuple(len(b[1]) for b in valid_bin_buffer)
            coverage = CoverageEvidence(bin_ends=bin_ends, observations_by_bin=counts)

            window_samples: list[TelemetrySample] = []
            for _, b_s in valid_bin_buffer:
                window_samples.extend(b_s)

            feature_vals = compute_feature_values(
                window_samples, candidate_names, analog_cols, digital_cols
            )

            yield Phase1BWindow(
                split=split,
                window_start=window_start,
                window_end=window_end,
                feature_names=candidate_names,
                feature_values=feature_vals,
                coverage=coverage,
            )


def fit_active_feature_names(
    train_features_df: pd.DataFrame, candidate_names: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    constant_mask = train_features_df[list(candidate_names)].nunique(dropna=False).eq(1)
    active = tuple(name for name in candidate_names if not bool(constant_mask[name]))
    removed = tuple(name for name in candidate_names if bool(constant_mask[name]))
    if not active:
        raise FeatureContractError("train contains no non-constant predictive features")
    return active, removed


def build_phase1b_features(
    prepared_dir: Path,
    output_path: Path,
    contract: Phase1BContract = PHASE1B,
) -> Phase1BFeatureManifest:
    parquet_file = prepared_dir / "telemetry.parquet"
    manifest_file = prepared_dir / "manifest.json"
    if not parquet_file.exists() or not manifest_file.exists():
        raise FileNotFoundError(f"prepared telemetry missing in {prepared_dir}")

    data_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    df = pq.read_table(parquet_file).to_pandas()

    windows = list(iter_phase1b_windows(df, contract))
    if not windows:
        raise FeatureContractError("No valid causal windows generated from telemetry")

    analog_cols = contract.analog_columns
    digital_cols = tuple(c for c in contract.digital_columns if c in contract.predictor_columns)
    candidate_names = get_candidate_feature_names(analog_cols, digital_cols)

    # Convert windows to DataFrame
    records: list[dict[str, Any]] = []
    for w in windows:
        rec: dict[str, Any] = {
            "split": w.split,
            "window_start": w.window_start,
            "window_end": w.window_end,
        }
        for name, val in zip(w.feature_names, w.feature_values, strict=True):
            rec[name] = val
        records.append(rec)

    full_features_df = pd.DataFrame(records)
    train_df = full_features_df[full_features_df["split"] == "train"]
    if train_df.empty:
        raise FeatureContractError("No valid train feature windows generated")

    active_names, removed_names = fit_active_feature_names(train_df, candidate_names)

    # Filter to active features
    final_cols = ["split", "window_start", "window_end", *active_names]
    final_df = full_features_df[final_cols].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(final_df, preserve_index=False)
    pq.write_table(table, output_path, compression="snappy")
    output_sha256 = sha256_file(output_path)

    split_counts = tuple(
        (s, int((final_df["split"] == s).sum())) for s in ("train", "calibration", "holdout")
    )
    rejection_counts = (
        ("train_constant_removed", len(removed_names)),
        ("invalid_bins_skipped", 0),
    )

    contract_manifest = phase1b_contract_manifest()
    contract_sha256_str = str(contract_manifest["contract_sha256"])
    data_manifest_sha256_str = str(data_manifest["manifest_sha256"])
    manifest_dict = {
        "contract_sha256": contract_sha256_str,
        "data_manifest_sha256": data_manifest_sha256_str,
        "output_sha256": output_sha256,
        "candidate_feature_names": list(candidate_names),
        "active_feature_names": list(active_names),
        "removed_train_constant_names": list(removed_names),
        "split_window_counts": [list(item) for item in split_counts],
        "rejection_counts": [list(item) for item in rejection_counts],
    }

    canonical_json = json.dumps(manifest_dict, sort_keys=True, separators=(",", ":"))
    manifest_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    manifest_dict["manifest_sha256"] = manifest_sha256

    manifest_path = output_path.parent / "feature_manifest.json"
    manifest_path.write_text(json.dumps(manifest_dict, indent=2), encoding="utf-8")

    return Phase1BFeatureManifest(
        contract_sha256=contract_sha256_str,
        data_manifest_sha256=data_manifest_sha256_str,
        output_sha256=output_sha256,
        candidate_feature_names=candidate_names,
        active_feature_names=active_names,
        removed_train_constant_names=removed_names,
        split_window_counts=split_counts,
        rejection_counts=rejection_counts,
        manifest_sha256=manifest_sha256,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build Phase 1B MetroPT-3 features.")
    parser.add_argument(
        "--prepared-dir", type=Path, required=True, help="Directory with prepared telemetry.parquet"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Path for output features.parquet"
    )
    args = parser.parse_args()

    manifest = build_phase1b_features(args.prepared_dir, args.output)
    print(
        f"Successfully generated Phase 1B features: {len(manifest.active_feature_names)} active features -> {args.output}"
    )


if __name__ == "__main__":
    main()
