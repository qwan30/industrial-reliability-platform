"""Causal, segment-local feature construction for the Phase 1 benchmark."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from industrial_reliability.contracts import PHASE1, Phase1Contract, contract_manifest
from industrial_reliability.data import DataContractError, sha256_file


@dataclass(frozen=True)
class FeatureManifest:
    contract_sha256: str
    data_manifest_sha256: str
    feature_columns: tuple[str, ...]
    total_windows: int
    windows_by_split: Mapping[str, int]
    rejected_windows_by_reason: Mapping[str, int]
    output_path: str
    output_sha256: str
    manifest_sha256: str


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _extract_with_rejections(
    frame: pd.DataFrame,
    contract: Phase1Contract,
) -> tuple[pd.DataFrame, dict[str, int]]:
    required = ("timestamp", *contract.predictor_columns)
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataContractError(f"segment is missing required columns: {missing}")
    if contract.window_seconds < 2 or contract.stride_seconds < 1:
        raise DataContractError("window_seconds must be at least 2 and stride_seconds positive")

    columns = ("window_start", "window_end", "split", *contract.feature_columns)
    window = contract.window_seconds
    candidates = np.arange(window - 1, len(frame), contract.stride_seconds, dtype=np.int64)
    if not len(candidates):
        return pd.DataFrame(columns=columns), {"split_boundary": 0, "timestamp_gap": 0}

    timestamps = pd.to_datetime(frame["timestamp"], errors="raise")
    invalid_delta = timestamps.diff().dt.total_seconds().ne(1).to_numpy()
    invalid_delta[0] = False
    invalid_prefix = np.cumsum(invalid_delta)
    starts = candidates - window + 1
    crosses_gap = (invalid_prefix[candidates] - invalid_prefix[starts]) != 0

    split_names = np.full(len(candidates), None, dtype=object)
    candidate_starts = timestamps.iloc[starts].reset_index(drop=True)
    candidate_ends = timestamps.iloc[candidates].reset_index(drop=True)
    for split in (contract.train, contract.calibration, contract.holdout):
        contained = (candidate_starts >= split.start) & (candidate_ends < split.end)
        split_names[contained.to_numpy() & ~crosses_gap] = split.name

    accepted = (~crosses_gap) & pd.notna(split_names)
    result = pd.DataFrame(
        {
            "window_start": candidate_starts[accepted].reset_index(drop=True),
            "window_end": candidate_ends[accepted].reset_index(drop=True),
            "split": split_names[accepted],
        }
    )

    for column in contract.analog_columns:
        values = frame[column].astype(float)
        rolling = values.rolling(window=window, min_periods=window)
        selected = candidates[accepted]
        statistics = {
            "last": values.to_numpy()[selected],
            "mean": rolling.mean().to_numpy()[selected],
            "std": rolling.std(ddof=contract.analog_std_ddof).to_numpy()[selected],
            "min": rolling.min().to_numpy()[selected],
            "max": rolling.max().to_numpy()[selected],
            "delta": values.to_numpy()[selected] - values.to_numpy()[selected - window + 1],
        }
        for statistic in contract.analog_statistics:
            result[f"{column}__{statistic}"] = statistics[statistic]

    for column in contract.digital_columns:
        values = frame[column].astype(float)
        changes = values.diff().ne(0).astype(float)
        changes.iloc[0] = 0.0
        selected = candidates[accepted]
        statistics = {
            "last": values.to_numpy()[selected],
            "active_ratio": values.rolling(window, min_periods=window)
            .mean()
            .to_numpy()[selected],
            "transition_count": changes.rolling(window - 1, min_periods=window - 1)
            .sum()
            .to_numpy()[selected],
        }
        for statistic in contract.digital_statistics:
            result[f"{column}__{statistic}"] = statistics[statistic]

    result = result.loc[:, columns]
    return result, {
        "split_boundary": int((~crosses_gap & pd.isna(split_names)).sum()),
        "timestamp_gap": int(crosses_gap.sum()),
    }


def extract_segment_features(
    frame: pd.DataFrame,
    contract: Phase1Contract,
) -> pd.DataFrame:
    """Return right-aligned features using only each decision's past segment rows."""
    result, _ = _extract_with_rejections(frame, contract)
    return result


def _feature_schema(contract: Phase1Contract) -> pa.Schema:
    return pa.schema(
        [
            pa.field("window_start", pa.timestamp("ns")),
            pa.field("window_end", pa.timestamp("ns")),
            pa.field("split", pa.string()),
            *(pa.field(column, pa.float64()) for column in contract.feature_columns),
        ]
    )


def _load_data_manifest(prepared_dir: Path, contract_sha256: str) -> dict[str, object]:
    manifest_path = prepared_dir / "manifest.json"
    manifest = cast(dict[str, object], json.loads(manifest_path.read_text(encoding="utf-8")))
    stored_hash = manifest.get("manifest_sha256")
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if not isinstance(stored_hash, str) or hashlib.sha256(_canonical_json(payload)).hexdigest() != stored_hash:
        raise DataContractError("prepared data manifest SHA-256 does not match its payload")
    if manifest.get("contract_sha256") != contract_sha256:
        raise DataContractError("prepared data contract SHA-256 does not match the feature contract")
    return manifest


def _feature_manifest_payload(
    *,
    contract_sha256: str,
    data_manifest_sha256: str,
    contract: Phase1Contract,
    total_windows: int,
    windows_by_split: Mapping[str, int],
    rejected_windows_by_reason: Mapping[str, int],
    output_path: str,
    output_sha256: str,
) -> dict[str, object]:
    return {
        "contract_sha256": contract_sha256,
        "data_manifest_sha256": data_manifest_sha256,
        "feature_columns": list(contract.feature_columns),
        "total_windows": total_windows,
        "windows_by_split": dict(windows_by_split),
        "rejected_windows_by_reason": dict(rejected_windows_by_reason),
        "output_path": output_path,
        "output_sha256": output_sha256,
    }


def build_features(
    prepared_dir: Path,
    output_path: Path,
    contract: Phase1Contract = PHASE1,
) -> FeatureManifest:
    """Read one prepared segment at a time and incrementally write its feature rows."""
    manifest_path = output_path.with_suffix(".manifest.json")
    if output_path.exists() or manifest_path.exists():
        raise FileExistsError(f"feature destination already exists: {output_path}")

    contract_sha256 = cast(str, contract_manifest(contract)["contract_sha256"])
    data_manifest = _load_data_manifest(prepared_dir, contract_sha256)
    data_manifest_sha256 = cast(str, data_manifest["manifest_sha256"])
    segments = data_manifest.get("segments")
    if not isinstance(segments, list):
        raise DataContractError("prepared data manifest segments must be a list")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.tmp-",
        dir=output_path.parent,
        delete=False,
    ) as temporary_handle:
        temporary_path = Path(temporary_handle.name)
    windows_by_split = {split.name: 0 for split in (contract.train, contract.calibration, contract.holdout)}
    rejected = {"split_boundary": 0, "timestamp_gap": 0}
    writer: pq.ParquetWriter | None = None

    try:
        schema = _feature_schema(contract)
        writer = pq.ParquetWriter(temporary_path, schema)
        prepared_root = prepared_dir.resolve()
        for segment in segments:
            if not isinstance(segment, dict) or not isinstance(segment.get("path"), str):
                raise DataContractError("prepared data manifest contains an invalid segment")
            segment_path = (prepared_dir / cast(str, segment["path"])).resolve()
            if not segment_path.is_relative_to(prepared_root):
                raise DataContractError("prepared segment path escapes its data directory")
            if sha256_file(segment_path) != segment.get("sha256"):
                raise DataContractError(f"prepared segment SHA-256 mismatch: {segment_path.name}")

            frame = pd.read_parquet(
                segment_path,
                columns=["timestamp", *contract.predictor_columns],
            )
            features, segment_rejected = _extract_with_rejections(frame, contract)
            for split_name, count in features["split"].value_counts().items():
                windows_by_split[cast(str, split_name)] += int(count)
            for reason, count in segment_rejected.items():
                rejected[reason] += count
            writer.write_table(pa.Table.from_pandas(features, schema=schema, preserve_index=False))

        writer.close()
        writer = None
        output_sha256 = sha256_file(temporary_path)
        total_windows = sum(windows_by_split.values())
        payload = _feature_manifest_payload(
            contract_sha256=contract_sha256,
            data_manifest_sha256=data_manifest_sha256,
            contract=contract,
            total_windows=total_windows,
            windows_by_split=windows_by_split,
            rejected_windows_by_reason=rejected,
            output_path=output_path.name,
            output_sha256=output_sha256,
        )
        manifest_sha256 = hashlib.sha256(_canonical_json(payload)).hexdigest()
        manifest_path.write_bytes(
            _canonical_json({**payload, "manifest_sha256": manifest_sha256}) + b"\n"
        )
        temporary_path.replace(output_path)
        return FeatureManifest(
            contract_sha256=contract_sha256,
            data_manifest_sha256=data_manifest_sha256,
            feature_columns=contract.feature_columns,
            total_windows=total_windows,
            windows_by_split=MappingProxyType(windows_by_split),
            rejected_windows_by_reason=MappingProxyType(rejected),
            output_path=output_path.name,
            output_sha256=output_sha256,
            manifest_sha256=manifest_sha256,
        )
    finally:
        if writer is not None:
            writer.close()
        temporary_path.unlink(missing_ok=True)
