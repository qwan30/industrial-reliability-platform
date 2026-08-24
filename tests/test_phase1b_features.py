from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from industrial_reliability.causal_features import TelemetrySample
from industrial_reliability.phase1b_contracts import PHASE1B
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


def test_six_valid_right_closed_bins_make_one_causal_window() -> None:
    start_time = datetime(2020, 2, 1, 0, 0, 0)
    samples = _generate_samples_for_bins((24, 24, 24, 24, 24, 24), start_time)
    windows = list(iter_phase1b_windows(samples, PHASE1B))

    assert len(windows) == 1
    assert windows[0].split == "train"
    assert windows[0].coverage.observations_by_bin == (24, 24, 24, 24, 24, 24)
    assert windows[0].window_end == start_time + timedelta(minutes=30)


def test_invalid_bin_closes_segment_without_filling() -> None:
    start_time = datetime(2020, 2, 1, 0, 0, 0)
    # 3rd bin has only 23 observations -> below min 24
    samples = _generate_samples_for_bins((24, 24, 23, 24, 24, 24, 24, 24, 24), start_time)
    windows = list(iter_phase1b_windows(samples, PHASE1B))

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
    # Setup mock prepared dir
    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir()

    # Create telemetry dataframe with 8 valid bins in train split
    start_time = datetime(2020, 2, 1, 0, 0, 0)
    samples = _generate_samples_for_bins((25, 25, 25, 25, 25, 25, 25, 25), start_time)

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
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, prepared_dir / "telemetry.parquet", compression="snappy")

    manifest = {"manifest_sha256": "mock_data_hash"}
    (prepared_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    out_parquet = tmp_path / "features" / "features.parquet"
    feat_manifest = build_phase1b_features(prepared_dir, out_parquet, PHASE1B)

    assert out_parquet.exists()
    assert (tmp_path / "features" / "feature_manifest.json").exists()
    assert len(feat_manifest.active_feature_names) > 0
