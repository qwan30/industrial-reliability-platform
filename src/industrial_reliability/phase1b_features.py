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

from industrial_reliability.artifact_integrity import verify_prepared_parquet
from industrial_reliability.causal_features import (
    CoverageEvidence,
    TelemetrySample,
    compute_feature_values,
    get_candidate_feature_names,
)
from industrial_reliability.contracts import Split
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


def _compute_bin_end(ts: datetime) -> datetime:
    minute_rem = ts.minute % 5
    if minute_rem == 0 and ts.second == 0 and ts.microsecond == 0:
        return ts
    minutes_to_add = 5 - minute_rem
    return ts.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)


def _extract_samples_from_input(
    frame_or_samples: pd.DataFrame | Sequence[TelemetrySample],
    analog_cols: tuple[str, ...],
    digital_cols: tuple[str, ...],
) -> list[TelemetrySample]:
    if not isinstance(frame_or_samples, pd.DataFrame):
        return list(frame_or_samples)

    df = frame_or_samples.sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        return []

    timestamps = df["timestamp"].tolist()
    analog_vals = df[list(analog_cols)].to_numpy(dtype=np.float64)
    digital_vals = df[list(digital_cols)].to_numpy(dtype=np.int8)

    return [
        TelemetrySample(
            timestamp=timestamps[i].to_pydatetime()
            if hasattr(timestamps[i], "to_pydatetime")
            else timestamps[i],
            analog=tuple(float(x) for x in analog_vals[i]),
            digital=tuple(int(x) for x in digital_vals[i]),
        )
        for i in range(len(df))
    ]


def _group_samples_into_bins(
    samples: Sequence[TelemetrySample],
) -> dict[datetime, list[TelemetrySample]]:
    bin_map: dict[datetime, list[TelemetrySample]] = {}
    for s in samples:
        b_end = _compute_bin_end(s.timestamp)
        if b_end not in bin_map:
            bin_map[b_end] = []
        bin_map[b_end].append(s)
    return bin_map


def _create_window_from_buffer(
    valid_bin_buffer: list[tuple[datetime, list[TelemetrySample]]],
    split: Literal["train", "calibration", "holdout"],
    candidate_names: tuple[str, ...],
    analog_cols: tuple[str, ...],
    digital_cols: tuple[str, ...],
    contract: Phase1BContract,
) -> Phase1BWindow:
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

    return Phase1BWindow(
        split=split,
        window_start=window_start,
        window_end=window_end,
        feature_names=candidate_names,
        feature_values=feature_vals,
        coverage=coverage,
    )


def _window_is_within_split(window: Phase1BWindow, split: Split) -> bool:
    return split.start <= window.window_start and window.window_end <= split.end


def _iter_phase1b_windows_with_stats(
    frame_or_samples: pd.DataFrame | Sequence[TelemetrySample],
    contract: Phase1BContract = PHASE1B,
) -> tuple[list[Phase1BWindow], int, int]:
    analog_cols = contract.analog_columns
    digital_cols = tuple(c for c in contract.digital_columns if c in contract.predictor_columns)
    candidate_names = get_candidate_feature_names(analog_cols, digital_cols)

    samples = _extract_samples_from_input(frame_or_samples, analog_cols, digital_cols)
    if not samples:
        return [], 0, 0

    bin_map = _group_samples_into_bins(samples)
    sorted_bin_ends = sorted(bin_map.keys())

    valid_bin_buffer: list[tuple[datetime, list[TelemetrySample]]] = []
    prev_bin_end: datetime | None = None
    invalid_bins_skipped = 0
    cross_split_windows_skipped = 0
    windows: list[Phase1BWindow] = []

    for b_end in sorted_bin_ends:
        bin_samples = bin_map[b_end]

        if len(bin_samples) < contract.min_bin_observations:
            invalid_bins_skipped += 1
            valid_bin_buffer.clear()
            prev_bin_end = None
            continue

        if prev_bin_end is not None:
            delta = (b_end - prev_bin_end).total_seconds()
            if delta != contract.stride_seconds:
                valid_bin_buffer.clear()

        valid_bin_buffer.append((b_end, bin_samples))
        prev_bin_end = b_end

        if len(valid_bin_buffer) > contract.lookback_bins:
            valid_bin_buffer.pop(0)

        if len(valid_bin_buffer) == contract.lookback_bins:
            window_end = valid_bin_buffer[-1][0]
            window_start = valid_bin_buffer[0][0] - timedelta(seconds=contract.stride_seconds)

            matched_split: Literal["train", "calibration", "holdout"] | None = None
            for split_name in ("train", "calibration", "holdout"):
                split_obj: Split = getattr(contract, split_name)
                if split_obj.start <= window_start and window_end <= split_obj.end:
                    matched_split = split_name
                    break

            if matched_split is None:
                cross_split_windows_skipped += 1
                continue

            window = _create_window_from_buffer(
                valid_bin_buffer,
                matched_split,
                candidate_names,
                analog_cols,
                digital_cols,
                contract,
            )
            split_obj = getattr(contract, matched_split)
            if _window_is_within_split(window, split_obj):
                windows.append(window)
            else:
                cross_split_windows_skipped += 1

    return windows, invalid_bins_skipped, cross_split_windows_skipped


def iter_phase1b_windows(
    frame_or_samples: pd.DataFrame | Sequence[TelemetrySample],
    contract: Phase1BContract = PHASE1B,
) -> Iterator[Phase1BWindow]:
    windows, _, _ = _iter_phase1b_windows_with_stats(frame_or_samples, contract)
    yield from windows


def fit_active_feature_names(
    train_features_df: pd.DataFrame, candidate_names: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    constant_mask = train_features_df[list(candidate_names)].nunique(dropna=False).eq(1)
    active = tuple(name for name in candidate_names if not bool(constant_mask[name]))
    removed = tuple(name for name in candidate_names if bool(constant_mask[name]))
    if not active:
        raise FeatureContractError("train contains no non-constant predictive features")
    return active, removed


def _windows_to_dataframe(windows: list[Phase1BWindow]) -> pd.DataFrame:
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
    df = pd.DataFrame(records)
    return df.sort_values(by="window_start").reset_index(drop=True)


def build_phase1b_features(
    prepared_dir: Path,
    output_path: Path,
    contract: Phase1BContract = PHASE1B,
) -> Phase1BFeatureManifest:
    resolved_prep = prepared_dir.resolve()
    parquet_file = (resolved_prep / "telemetry.parquet").resolve()
    manifest_file = (resolved_prep / "manifest.json").resolve()
    if not parquet_file.is_file() or not manifest_file.is_file():
        raise FileNotFoundError(f"prepared telemetry missing in {resolved_prep}")

    contract_manifest = phase1b_contract_manifest()
    contract_sha256_str = str(contract_manifest["contract_sha256"])
    prep_identity = verify_prepared_parquet(parquet_file, contract_sha256_str)

    df = pq.read_table(parquet_file).to_pandas()

    windows, invalid_bins_skipped, cross_split_windows_skipped = _iter_phase1b_windows_with_stats(
        df, contract
    )
    if not windows:
        raise FeatureContractError("No valid causal windows generated from telemetry")

    analog_cols = contract.analog_columns
    digital_cols = tuple(c for c in contract.digital_columns if c in contract.predictor_columns)
    candidate_names = get_candidate_feature_names(analog_cols, digital_cols)

    full_features_df = _windows_to_dataframe(windows)
    train_df = full_features_df[full_features_df["split"] == "train"]
    if train_df.empty:
        raise FeatureContractError("No valid train feature windows generated")

    active_names, removed_names = fit_active_feature_names(train_df, candidate_names)

    final_cols = ["split", "window_start", "window_end", *active_names]
    final_df = full_features_df[final_cols].copy()

    resolved_out = output_path.resolve()
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(final_df, preserve_index=False)
    pq.write_table(table, resolved_out, compression="snappy")
    output_sha256 = sha256_file(resolved_out)

    split_counts = tuple(
        (s, int((final_df["split"] == s).sum())) for s in ("train", "calibration", "holdout")
    )
    rejection_counts = (
        ("train_constant_removed", len(removed_names)),
        ("invalid_bins_skipped", invalid_bins_skipped),
        ("cross_split_windows_skipped", cross_split_windows_skipped),
    )

    data_manifest_sha256_str = prep_identity.manifest_sha256
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

    manifest_path = (resolved_out.parent / "feature_manifest.json").resolve()
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
        "--prepared-dir",
        type=Path,
        required=True,
        help="Directory with prepared telemetry.parquet",
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
