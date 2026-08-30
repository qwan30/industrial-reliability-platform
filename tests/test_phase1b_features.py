from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from industrial_reliability.artifact_integrity import ArtifactIntegrityError
from industrial_reliability.causal_features import TelemetrySample
from industrial_reliability.phase1b_contracts import PHASE1C, metropt3_contract_manifest
from industrial_reliability.phase1b_data import sha256_file
from industrial_reliability.phase1b_features import (
    build_phase1b_features,
    fit_active_feature_names,
    iter_phase1b_windows,
)


def _generate_samples_for_bins(
    counts: tuple[int, ...], start_bin: datetime
) -> list[TelemetrySample]:
    samples = []
    for bin_idx, count in enumerate(counts):
        bin_end = start_bin + timedelta(minutes=5 * (bin_idx + 1))
        for obs_idx in range(count):
            # timestamps within (bin_end - 5m, bin_end]
            ts = (
                bin_end
                - timedelta(minutes=5)
                + timedelta(seconds=int(obs_idx * (300 / max(count, 1))))
                + timedelta(seconds=1)
            )
            analog = (1.0 + bin_idx, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0)
            digital = (1, 0, 1, 0, 1, 0, 1)  # 7 digital predictor columns
            samples.append(TelemetrySample(ts, analog, digital))
    return samples


def _create_prepared_dir(tmp_path: Path, samples: list[TelemetrySample]) -> Path:
    prep_dir = tmp_path / "prepared"
    prep_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for s in samples:
        row = {
            "timestamp": s.timestamp,
            "tp2": s.analog[0],
            "tp3": s.analog[1],
            "h1": s.analog[2],
            "dv_pressure": s.analog[3],
            "reservoirs": s.analog[4],
            "oil_temperature": s.analog[5],
            "motor_current": s.analog[6],
            "comp": s.digital[0],
            "dv_electric": s.digital[1],
            "towers": s.digital[2],
            "mpg": s.digital[3],
            "pressure_switch": s.digital[4],
            "oil_level": s.digital[5],
            "caudal_impulses": s.digital[6],
            "lps": 0,
        }
        records.append(row)
    df = pd.DataFrame(records)
    parquet_path = prep_dir / "telemetry.parquet"
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, parquet_path, compression="snappy")
    output_sha256 = sha256_file(parquet_path)

    contract_manifest = metropt3_contract_manifest(PHASE1C)
    manifest_data = {
        "archive_sha256": PHASE1C.archive_sha256,
        "contract_sha256": contract_manifest["contract_sha256"],
        "output_sha256": output_sha256,
        "normalized_rows": len(records),
        "canonical_columns": list(PHASE1C.canonical_columns),
        "identical_duplicates_removed": 0,
        "first_timestamp": records[0]["timestamp"].isoformat(),
        "last_timestamp": records[-1]["timestamp"].isoformat(),
    }
    canonical = json.dumps(manifest_data, sort_keys=True, separators=(",", ":"))
    manifest_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    manifest_data["manifest_sha256"] = manifest_sha256
    (prep_dir / "manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    return prep_dir


def test_six_valid_right_closed_bins_make_one_causal_window() -> None:
    start_time = datetime(2020, 2, 1, 0, 0, 0)
    samples = _generate_samples_for_bins((24, 24, 24, 24, 24, 24), start_time)
    windows = list(iter_phase1b_windows(samples, PHASE1C))

    assert len(windows) == 1
    assert windows[0].split == "train"
    assert windows[0].coverage.observations_by_bin == (24, 24, 24, 24, 24, 24)
    assert windows[0].window_end == start_time + timedelta(minutes=30)


def test_invalid_bin_closes_segment_without_filling() -> None:
    start_time = datetime(2020, 2, 1, 0, 0, 0)
    # 3rd bin has only 23 observations -> below min 24
    samples = _generate_samples_for_bins((24, 24, 23, 24, 24, 24, 24, 24, 24), start_time)
    windows = list(iter_phase1b_windows(samples, PHASE1C))

    # After the 23-count bin, there are only 6 bins: indices 3, 4, 5, 6, 7, 8 (6 bins)
    # so we should get exactly 1 window at the end!
    assert len(windows) == 1


def test_fit_active_feature_names_removes_constant_columns() -> None:
    df = pd.DataFrame(
        {
            "f_const": [1.0, 1.0, 1.0],
            "f_varying": [1.0, 2.0, 3.0],
        }
    )
    active, removed = fit_active_feature_names(df, ("f_const", "f_varying"))
    assert active == ("f_varying",)
    assert removed == ("f_const",)


def test_build_phase1b_features_e2e(tmp_path: Path) -> None:
    start_time = datetime(2020, 2, 1, 0, 0, 0)
    samples = _generate_samples_for_bins((25, 25, 25, 25, 25, 25, 25, 25), start_time)
    prepared_dir = _create_prepared_dir(tmp_path, samples)
    prep_sha = sha256_file(prepared_dir / "telemetry.parquet")

    out_parquet = tmp_path / "features" / "features.parquet"
    feat_manifest = build_phase1b_features(
        prepared_dir,
        out_parquet,
        expected_prepared_output_sha256=prep_sha,
        contract=PHASE1C,
    )

    assert out_parquet.exists()
    assert (tmp_path / "features" / "feature_manifest.json").exists()
    assert len(feat_manifest.active_feature_names) > 0


def test_build_features_rejects_tampered_prepared_parquet(tmp_path: Path) -> None:
    start_time = datetime(2020, 2, 1, 0, 0, 0)
    samples = _generate_samples_for_bins((25, 25, 25, 25, 25, 25, 25, 25), start_time)
    prepared_dir = _create_prepared_dir(tmp_path, samples)
    prep_sha = sha256_file(prepared_dir / "telemetry.parquet")

    parquet_file = prepared_dir / "telemetry.parquet"
    # Tamper telemetry parquet by appending a byte
    with parquet_file.open("ab") as f:
        f.write(b"X")

    out_parquet = tmp_path / "features" / "features.parquet"
    with pytest.raises(ArtifactIntegrityError, match=r"telemetry\.parquet SHA-256 mismatch"):
        build_phase1b_features(
            prepared_dir,
            out_parquet,
            expected_prepared_output_sha256=prep_sha,
            contract=PHASE1C,
        )


def test_window_never_crosses_train_calibration_boundary() -> None:
    samples = _generate_samples_for_bins(
        (24, 24, 24, 24, 24, 24, 24),
        datetime(2020, 2, 21, 23, 30),
    )
    windows = list(iter_phase1b_windows(samples, PHASE1C))
    assert all(
        window.split != "calibration" or window.window_start >= PHASE1C.calibration.start
        for window in windows
    )


def test_windows_spanning_across_splits_are_skipped() -> None:
    # 12 bins starting 2020-02-21 23:30 (6 train bins ending 23:35..00:00, 6 calib bins ending 00:05..00:30)
    samples = _generate_samples_for_bins((24,) * 12, datetime(2020, 2, 21, 23, 30))
    windows = list(iter_phase1b_windows(samples, PHASE1C))
    assert len(windows) == 2
    assert windows[0].split == "train"
    assert windows[0].window_start == datetime(2020, 2, 21, 23, 30)
    assert windows[0].window_end == datetime(2020, 2, 22, 0, 0)
    assert windows[1].split == "calibration"
    assert windows[1].window_start == datetime(2020, 2, 22, 0, 0)
    assert windows[1].window_end == datetime(2020, 2, 22, 0, 30)


def test_build_phase1b_features_manifest_records_actual_rejection_counts(tmp_path: Path) -> None:
    # 7 train bins (ends 23:30..00:00 -> 2 train windows), 6 calib bins (ends 00:05..00:30 -> 1 calib window), 1 invalid bin (10 obs), 6 calib bins
    start_time = datetime(2020, 2, 21, 23, 25)
    counts = (24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 10, 24, 24, 24, 24, 24, 24)
    samples = _generate_samples_for_bins(counts, start_time)
    prepared_dir = _create_prepared_dir(tmp_path, samples)
    prep_sha = sha256_file(prepared_dir / "telemetry.parquet")

    out_parquet = tmp_path / "features" / "features.parquet"
    feat_manifest = build_phase1b_features(
        prepared_dir,
        out_parquet,
        expected_prepared_output_sha256=prep_sha,
        contract=PHASE1C,
    )

    rejection_dict = dict(feat_manifest.rejection_counts)
    assert rejection_dict["invalid_bins_skipped"] == 1
    assert rejection_dict["cross_split_windows_skipped"] == 5
    assert "train_constant_removed" in rejection_dict

    manifest_json_path = tmp_path / "features" / "feature_manifest.json"
    manifest_data = json.loads(manifest_json_path.read_text(encoding="utf-8"))
    json_rejection_dict = dict(manifest_data["rejection_counts"])
    assert json_rejection_dict["invalid_bins_skipped"] == 1
    assert json_rejection_dict["cross_split_windows_skipped"] == 5
