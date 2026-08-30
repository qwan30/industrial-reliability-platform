from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from industrial_reliability.artifact_integrity import ArtifactIntegrityError
from industrial_reliability.phase1b_benchmark import (
    MODEL_IDS,
    FittedCandidate,
    detector_for,
    fit_phase1b_candidate,
    publish_phase1b_results,
    run_phase1b_benchmark,
)
from industrial_reliability.phase1b_contracts import PHASE1C, metropt3_contract_manifest
from industrial_reliability.phase1b_data import sha256_file


def test_detector_for_instantiates_all_models() -> None:
    for model_id in MODEL_IDS:
        det = detector_for(model_id, PHASE1C)
        assert det is not None


def test_fit_phase1b_candidate_produces_locked_threshold() -> None:
    rng = np.random.default_rng(42)
    train = rng.normal(0, 1, size=(50, 4))
    calib = rng.normal(0, 1, size=(20, 4))

    fitted = fit_phase1b_candidate(
        model_id="statistical",
        train_features=train,
        calibration_features=calib,
        contract=PHASE1C,
    )
    assert isinstance(fitted, FittedCandidate)
    assert np.isfinite(fitted.threshold)
    assert fitted.threshold_provenance.split == "calibration"
    assert fitted.threshold_provenance.quantile == 0.995


def _create_synthetic_benchmark_fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = prepared_dir / "telemetry.parquet"

    # Create minimal telemetry parquet
    tel_df = pd.DataFrame(
        {
            "timestamp": [datetime(2020, 2, 1, 0, 0)],
            "tp2": [1.0],
            "tp3": [2.0],
            "h1": [3.0],
            "dv_pressure": [4.0],
            "reservoirs": [5.0],
            "oil_temperature": [6.0],
            "motor_current": [7.0],
            "comp": [1],
            "dv_electric": [0],
            "towers": [1],
            "mpg": [0],
            "pressure_switch": [1],
            "oil_level": [0],
            "caudal_impulses": [1],
            "lps": [0],
        }
    )
    pq.write_table(pa.Table.from_pandas(tel_df), telemetry_path, compression="snappy")
    tel_sha = sha256_file(telemetry_path)
    contract_manifest = metropt3_contract_manifest(PHASE1C)
    contract_sha = str(contract_manifest["contract_sha256"])

    prep_data = {
        "archive_sha256": "1" * 64,
        "contract_sha256": contract_sha,
        "output_sha256": tel_sha,
        "normalized_rows": 1,
        "canonical_columns": list(PHASE1C.canonical_columns),
        "identical_duplicates_removed": 0,
        "first_timestamp": "2020-02-01T00:00:00",
        "last_timestamp": "2020-02-01T00:00:00",
    }
    canonical_prep = json.dumps(prep_data, sort_keys=True, separators=(",", ":"))
    prep_data_manifest_sha = hashlib.sha256(canonical_prep.encode("utf-8")).hexdigest()
    prep_data["manifest_sha256"] = prep_data_manifest_sha
    (prepared_dir / "manifest.json").write_text(json.dumps(prep_data, indent=2), encoding="utf-8")

    feature_dir = tmp_path / "features"
    feature_dir.mkdir(parents=True, exist_ok=True)
    feat_path = feature_dir / "features.parquet"

    # Create dummy windows for train, calib, holdout
    feature_names = ["f1", "f2"]
    records = []

    # Train: 2020-02-05
    for i in range(20):
        ts = datetime(2020, 2, 5, 0, 0) + timedelta(minutes=5 * i)
        records.append(
            {
                "split": "train",
                "window_start": ts,
                "window_end": ts + timedelta(minutes=30),
                "f1": 1.0 + i * 0.01,
                "f2": 2.0,
            }
        )

    # Calib: 2020-02-25
    for i in range(20):
        ts = datetime(2020, 2, 25, 0, 0) + timedelta(minutes=5 * i)
        records.append(
            {
                "split": "calibration",
                "window_start": ts,
                "window_end": ts + timedelta(minutes=30),
                "f1": 1.0 + i * 0.01,
                "f2": 2.0,
            }
        )

    # Holdout: normal days (2020-03-10)
    for i in range(20):
        ts = datetime(2020, 3, 10, 0, 0) + timedelta(minutes=5 * i)
        records.append(
            {
                "split": "holdout",
                "window_start": ts,
                "window_end": ts + timedelta(minutes=30),
                "f1": 1.0 + i * 0.01,
                "f2": 2.0,
            }
        )

    # Holdout: 2020-04-18 (matches event 1)
    for i in range(50):
        ts = datetime(2020, 4, 18, 0, 0) + timedelta(minutes=5 * i)
        records.append(
            {
                "split": "holdout",
                "window_start": ts,
                "window_end": ts + timedelta(minutes=30),
                "f1": 5.0 + i * 0.1,
                "f2": 2.0,
            }
        )

    # Add holdout windows across the remaining 3 events
    for event_dt in (
        datetime(2020, 5, 30, 0, 0),
        datetime(2020, 6, 6, 0, 0),
        datetime(2020, 7, 15, 15, 0),
    ):
        for i in range(10):
            ts = event_dt + timedelta(minutes=5 * i)
            records.append(
                {
                    "split": "holdout",
                    "window_start": ts,
                    "window_end": ts + timedelta(minutes=30),
                    "f1": 10.0 + i * 0.1,
                    "f2": 2.0,
                }
            )

    df = pd.DataFrame(records)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, feat_path, compression="snappy")
    feat_sha = sha256_file(feat_path)

    feat_manifest_dict = {
        "contract_sha256": contract_sha,
        "data_manifest_sha256": prep_data_manifest_sha,
        "output_sha256": feat_sha,
        "candidate_feature_names": feature_names,
        "active_feature_names": feature_names,
        "removed_train_constant_names": [],
        "split_window_counts": [["train", 20], ["calibration", 20], ["holdout", 100]],
        "rejection_counts": [["train_constant_removed", 0], ["invalid_bins_skipped", 0]],
    }
    canonical_feat = json.dumps(feat_manifest_dict, sort_keys=True, separators=(",", ":"))
    feat_manifest_sha = hashlib.sha256(canonical_feat.encode("utf-8")).hexdigest()
    feat_manifest_dict["manifest_sha256"] = feat_manifest_sha
    (feature_dir / "feature_manifest.json").write_text(
        json.dumps(feat_manifest_dict, indent=2), encoding="utf-8"
    )

    return prepared_dir, feat_path, tmp_path / "artifacts"


def test_run_phase1b_benchmark_end_to_end_synthetic(tmp_path: Path) -> None:
    prepared_dir, feat_path, artifact_dir = _create_synthetic_benchmark_fixtures(tmp_path)
    res = run_phase1b_benchmark(
        prepared_dir=prepared_dir,
        feature_path=feat_path,
        artifact_dir=artifact_dir,
        contract=PHASE1C,
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


def test_benchmark_rejects_tampered_features(tmp_path: Path) -> None:
    prepared_dir, feat_path, artifact_dir = _create_synthetic_benchmark_fixtures(tmp_path)

    # Tamper features.parquet
    with feat_path.open("ab") as f:
        f.write(b"CORRUPTED_BYTES")

    with pytest.raises(ArtifactIntegrityError, match=r"features\.parquet SHA-256 mismatch"):
        run_phase1b_benchmark(
            prepared_dir=prepared_dir,
            feature_path=feat_path,
            artifact_dir=artifact_dir,
            contract=PHASE1C,
        )
