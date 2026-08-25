from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mlflow")

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    write_promotion_receipt,
)
from industrial_reliability.models import RobustStatisticalDetector
from industrial_reliability.package_champion import build_champion_package
from industrial_reliability.phase1b_data import sha256_file
from industrial_reliability.phase7_gate import Phase7GateResult, run_phase7_gate


def _setup_test_champion(base_dir: Path) -> tuple[Path, Path, Path]:
    run_dir = base_dir / "run-001"
    run_dir.mkdir(parents=True, exist_ok=True)
    models_dir = run_dir / "models"
    models_dir.mkdir(exist_ok=True)

    feature_names = ["tp2_mean", "dv_pressure_mean"]
    train_data = np.array([[1.0 + i * 0.5, 2.0 + i * 0.5] for i in range(5)], dtype=np.float64)
    detector = RobustStatisticalDetector().fit(train_data)
    model_path = models_dir / "statistical.joblib"
    joblib.dump(detector, model_path)

    median = np.median(train_data, axis=0)
    mad = np.median(np.abs(train_data - median), axis=0)
    baseline_path = run_dir / "evidence-baseline.npz"
    np.savez_compressed(
        baseline_path,
        feature_names=np.array(feature_names),
        median=median,
        mad=mad,
    )

    from industrial_reliability.phase1b_benchmark import calibrate_threshold
    from industrial_reliability.phase1b_contracts import PHASE1B

    calib_matrix = np.array(
        [[1.0 + i * 0.5, 2.0 + i * 0.5] for i in range(5, 10)], dtype=np.float64
    )
    calib_scores_arr = detector.score(calib_matrix)
    computed_threshold = float(calibrate_threshold(calib_scores_arr, PHASE1B))

    feat_records = []
    scores_records = []
    from datetime import datetime, timedelta

    base_ts = datetime(2020, 2, 25, 0, 0)
    for i in range(10):
        ts_start = base_ts + timedelta(minutes=5 * i)
        ts_end = ts_start + timedelta(minutes=30)
        val_tp2 = 1.0 + i * 0.5
        val_dv = 2.0 + i * 0.5
        feat_vec = np.array([[val_tp2, val_dv]], dtype=np.float64)
        sc = float(detector.score(feat_vec)[0])
        feat_records.append(
            {
                "split": "train" if i < 5 else "calibration",
                "window_start": ts_start,
                "window_end": ts_end,
                "tp2_mean": val_tp2,
                "dv_pressure_mean": val_dv,
            }
        )
        scores_records.append(
            {
                "model_id": "statistical",
                "split": "calibration",
                "window_start": ts_start,
                "window_end": ts_end,
                "score": sc,
                "threshold": computed_threshold,
                "is_anomaly": sc >= computed_threshold,
            }
        )

    feat_path = base_dir / "features.parquet"
    feat_table = pa.Table.from_pandas(pd.DataFrame(feat_records), preserve_index=False)
    pq.write_table(feat_table, feat_path, compression="snappy")

    scores_path = run_dir / "scores.parquet"
    scores_table = pa.Table.from_pandas(pd.DataFrame(scores_records), preserve_index=False)
    pq.write_table(scores_table, scores_path, compression="snappy")

    champion_manifest = {
        "schema_version": "phase1b-champion-v1",
        "run_id": "run-001",
        "verdict": "FEASIBLE",
        "model_id": "statistical",
        "model_version": "champion-statistical-v1",
        "threshold": computed_threshold,
        "threshold_provenance": {
            "split": "calibration",
            "quantile": 0.995,
            "method": "higher",
        },
        "active_feature_names": feature_names,
        "contract_sha256": "a" * 64,
        "source_dataset_sha256": "b" * 64,
        "feature_output_sha256": sha256_file(feat_path),
        "artifact_sha256": {
            "scores_parquet": sha256_file(scores_path),
            "model_binary": sha256_file(model_path),
            "evidence_baseline": sha256_file(baseline_path),
        },
    }
    (run_dir / "champion-manifest.json").write_text(
        json.dumps(champion_manifest, indent=2), encoding="utf-8"
    )

    pkg_dir = base_dir / "champion"
    build_champion_package(run_dir, feat_path, pkg_dir)

    receipt = PromotionReceiptV1(
        schema_version="mlflow-promotion-receipt-v1",
        mlflow_run_id="run-mlflow-001",
        registered_model_name="industrial-reliability-anomaly-detector",
        registered_model_version="1",
        alias="champion",
        model_version="champion-statistical-v1",
        dataset_sha256="b" * 64,
        contract_sha256="a" * 64,
        champion_package_sha256=sha256_file(pkg_dir / "manifest.json"),
        source_git_sha="0" * 40,
        approver="reliability-engineer",
        promoted_at="2026-08-25T00:00:00Z",
        receipt_sha256="",
    ).with_computed_hash()
    write_promotion_receipt(pkg_dir / "promotion-receipt.json", receipt)

    return run_dir, feat_path, pkg_dir


def test_full_phase7_gate_certification(tmp_path: Path) -> None:
    db_path = tmp_path / "mlflow.db"
    tracking_uri = f"sqlite:///{db_path.as_posix()}"
    run_dir, feat_path, pkg_dir = _setup_test_champion(tmp_path)

    out_dir = tmp_path / "artifacts" / "phase7"
    gate_res = run_phase7_gate(
        champion_package=pkg_dir,
        features_path=feat_path,
        phase1b_run_dir=run_dir,
        output_dir=out_dir,
        tracking_uri=tracking_uri,
    )

    assert isinstance(gate_res, Phase7GateResult)
    assert gate_res.reasons == []
    assert gate_res.verdict == "PASS"
    assert gate_res.threshold_delta <= 1e-9
    assert gate_res.golden_scores_max_delta <= 1e-6
    report_file = out_dir / gate_res.source_git_sha / "phase7-gate.json"
    assert report_file.is_file()
