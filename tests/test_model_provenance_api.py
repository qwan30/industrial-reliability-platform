from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

from fastapi.testclient import TestClient
import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from industrial_reliability.api import create_app
from industrial_reliability.champion import ChampionProvenanceVerifier, load_champion
from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    canonical_dumps,
    write_promotion_receipt,
)
from industrial_reliability.models import RobustStatisticalDetector
from industrial_reliability.package_champion import build_champion_package
from industrial_reliability.phase1b_data import sha256_file


def _setup_test_champion(base_dir: Path) -> tuple[Path, Path, Path]:
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


def test_readyz_passes_when_provenance_valid(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ready"


def test_readyz_fails_503_on_missing_receipt(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    (pkg_dir / "promotion-receipt.json").unlink()

    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "CHAMPION_PROVENANCE_MISMATCH"


def test_readyz_fails_503_on_tampered_receipt(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    receipt_data = json.loads((pkg_dir / "promotion-receipt.json").read_text(encoding="utf-8"))
    receipt_data["approver"] = "malicious-actor"
    (pkg_dir / "promotion-receipt.json").write_text(json.dumps(receipt_data), encoding="utf-8")

    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "CHAMPION_PROVENANCE_MISMATCH"


def test_readyz_fails_503_on_mlflow_alias_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)

    mock_client = Mock()
    mock_mv = Mock()
    mock_mv.run_id = "different-run-id"
    mock_client.get_model_version_by_alias.return_value = mock_mv

    verifier = ChampionProvenanceVerifier(
        package_dir=pkg_dir,
        tracking_uri="http://127.0.0.1:5000",
        mlflow_client=mock_client,
    )

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "CHAMPION_PROVENANCE_MISMATCH"


def test_get_model_provenance_endpoint(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get(f"/v1/models/{scorer.model_version}/provenance")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "manifest" in data
    assert "receipt" in data
    assert data["manifest"]["model_version"] == "champion-statistical-v1"

    # Test unknown version returns 404
    resp_404 = client.get("/v1/models/unknown-version-v9/provenance")
    assert resp_404.status_code == 404
    assert resp_404.json()["error"]["code"] == "MODEL_VERSION_NOT_FOUND"


def test_get_model_provenance_scrubs_secrets(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get(f"/v1/models/{scorer.model_version}/provenance")
    assert resp.status_code == 200
    raw_text = resp.text.lower()
    for sensitive_keyword in ["password", "secret", "token", "postgres://", "api_key"]:
        assert sensitive_keyword not in raw_text
