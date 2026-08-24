from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from industrial_reliability.ml_lifecycle import (
    CandidateResult,
    ImportCandidateRequest,
    PromotionRequest,
    import_candidate,
    promote_candidate,
)
from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    load_promotion_receipt,
    verify_promotion_receipt,
)
from industrial_reliability.models import RobustStatisticalDetector
from industrial_reliability.package_champion import build_champion_package
from industrial_reliability.phase1b_data import sha256_file


def _setup_test_run(base_dir: Path) -> tuple[Path, Path, Path]:
    run_dir = base_dir / "run-001"
    run_dir.mkdir(parents=True, exist_ok=True)
    models_dir = run_dir / "models"
    models_dir.mkdir(exist_ok=True)

    feature_names = ["tp2_mean", "dv_pressure_mean"]
    train_data = np.array([[1.0, 2.0], [1.1, 2.1], [0.9, 1.9]], dtype=np.float64)
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
                "threshold": 1.0,
                "is_anomaly": sc >= 1.0,
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
        "threshold": 1.0,
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

    return run_dir, feat_path, pkg_dir


def test_promote_candidate_sqlite_tracking(tmp_path: Path) -> None:
    db_path = tmp_path / "mlflow.db"
    tracking_uri = f"sqlite:///{db_path.as_posix()}"
    run_dir, feat_path, pkg_dir = _setup_test_run(tmp_path)

    # 1. Import candidate
    import_req = ImportCandidateRequest(
        champion_package=pkg_dir,
        phase1b_run_dir=run_dir,
        tracking_uri=tracking_uri,
    )
    import_res = import_candidate(import_req)

    # 2. Promote candidate
    receipt_out = tmp_path / "promotion-receipt.json"
    promote_req = PromotionRequest(
        run_id=import_res.run_id,
        approver="lead-engineer",
        expected_source_git_sha=import_res.provenance.source_git_sha,
        output=receipt_out,
        champion_package=pkg_dir,
        tracking_uri=tracking_uri,
    )
    receipt = promote_candidate(promote_req)
    assert isinstance(receipt, PromotionReceiptV1)
    assert receipt_out.is_file()

    # 3. Verify receipt verification
    loaded_receipt = load_promotion_receipt(receipt_out)
    assert loaded_receipt.mlflow_run_id == import_res.run_id
    verify_promotion_receipt(loaded_receipt)
