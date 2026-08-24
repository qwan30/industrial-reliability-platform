from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from industrial_reliability.phase1b_benchmark import (
    MODEL_IDS,
    FittedCandidate,
    detector_for,
    fit_phase1b_candidate,
    publish_phase1b_results,
    run_phase1b_benchmark,
)
from industrial_reliability.phase1b_contracts import PHASE1B


def test_detector_for_instantiates_all_models() -> None:
    for model_id in MODEL_IDS:
        det = detector_for(model_id, PHASE1B)
        assert det is not None


def test_fit_phase1b_candidate_produces_locked_threshold() -> None:
    rng = np.random.default_rng(42)
    train = rng.normal(0, 1, size=(50, 4))
    calib = rng.normal(0, 1, size=(20, 4))

    fitted = fit_phase1b_candidate(
        model_id="statistical",
        train_features=train,
        calibration_features=calib,
        contract=PHASE1B,
    )
    assert isinstance(fitted, FittedCandidate)
    assert np.isfinite(fitted.threshold)
    assert fitted.threshold_provenance.split == "calibration"
    assert fitted.threshold_provenance.quantile == 0.995


def test_run_phase1b_benchmark_end_to_end_synthetic(tmp_path: Path) -> None:
    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir()
    (prepared_dir / "manifest.json").write_text(
        json.dumps({"manifest_sha256": "mock_data_sha", "archive_sha256": "mock_arch_sha", "output_sha256": "mock_out_sha"}),
        encoding="utf-8",
    )

    feature_dir = tmp_path / "features"
    feature_dir.mkdir()
    feat_path = feature_dir / "features.parquet"

    # Create dummy windows for train, calib, holdout
    feature_names = ["f1", "f2"]
    records = []

    # Train: 2020-02-05
    for i in range(20):
        ts = datetime(2020, 2, 5, 0, 0) + timedelta(minutes=5 * i)
        records.append({"split": "train", "window_start": ts, "window_end": ts + timedelta(minutes=30), "f1": 1.0 + i * 0.01, "f2": 2.0})

    # Calib: 2020-02-25
    for i in range(20):
        ts = datetime(2020, 2, 25, 0, 0) + timedelta(minutes=5 * i)
        records.append({"split": "calibration", "window_start": ts, "window_end": ts + timedelta(minutes=30), "f1": 1.0 + i * 0.01, "f2": 2.0})

    # Holdout: normal days (2020-03-10)
    for i in range(20):
        ts = datetime(2020, 3, 10, 0, 0) + timedelta(minutes=5 * i)
        records.append({"split": "holdout", "window_start": ts, "window_end": ts + timedelta(minutes=30), "f1": 1.0 + i * 0.01, "f2": 2.0})

    # Holdout: 2020-04-18 (matches event 1)
    for i in range(50):
        ts = datetime(2020, 4, 18, 0, 0) + timedelta(minutes=5 * i)
        records.append({"split": "holdout", "window_start": ts, "window_end": ts + timedelta(minutes=30), "f1": 5.0 + i * 0.1, "f2": 2.0})

    # Add holdout windows across the remaining 3 events
    for event_dt in (datetime(2020, 5, 30, 0, 0), datetime(2020, 6, 6, 0, 0), datetime(2020, 7, 15, 15, 0)):
        for i in range(10):
            ts = event_dt + timedelta(minutes=5 * i)
            records.append({"split": "holdout", "window_start": ts, "window_end": ts + timedelta(minutes=30), "f1": 10.0 + i * 0.1, "f2": 2.0})

    df = pd.DataFrame(records)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, feat_path, compression="snappy")

    (feature_dir / "feature_manifest.json").write_text(
        json.dumps({
            "contract_sha256": "mock_contract_sha",
            "active_feature_names": feature_names,
            "output_sha256": "mock_feat_sha",
        }),
        encoding="utf-8",
    )

    artifact_dir = tmp_path / "artifacts"
    res = run_phase1b_benchmark(
        prepared_dir=prepared_dir,
        feature_path=feat_path,
        artifact_dir=artifact_dir,
        contract=PHASE1B,
    )

    assert res.verdict in ("FEASIBLE", "NOT FEASIBLE")
    assert (res.run_dir / "run_manifest.json").exists()
    assert (res.run_dir / "scores.parquet").exists()
    assert (res.run_dir / "evidence-baseline.npz").exists()

    # Test publish
    out_docs = tmp_path / "docs_results"
    metrics_p, report_p = publish_phase1b_results(res.run_dir, out_docs)
    assert metrics_p.exists()
    assert report_p.exists()
