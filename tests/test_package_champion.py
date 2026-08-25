from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from industrial_reliability.models import RobustStatisticalDetector
from industrial_reliability.package_champion import (
    ChampionPackageError,
    build_champion_package,
)
from industrial_reliability.phase1b_data import sha256_file


def _create_mock_feasible_phase1b_run(
    base_dir: Path,
) -> tuple[Path, Path]:
    run_dir = base_dir / "run-001"
    run_dir.mkdir(parents=True)
    models_dir = run_dir / "models"
    models_dir.mkdir()

    feature_names = ["tp2_mean", "dv_pressure_mean"]
    # 1. Fit mock detector
    train_data = np.array([[1.0, 2.0], [1.1, 2.1], [0.9, 1.9]], dtype=np.float64)
    detector = RobustStatisticalDetector().fit(train_data)
    model_path = models_dir / "statistical.joblib"
    joblib.dump(detector, model_path)

    # 2. Evidence baseline
    median = np.median(train_data, axis=0)
    mad = np.median(np.abs(train_data - median), axis=0)
    baseline_path = run_dir / "evidence-baseline.npz"
    np.savez_compressed(
        baseline_path,
        feature_names=np.array(feature_names),
        median=median,
        mad=mad,
    )

    # 3. Features Parquet
    feat_records = []
    scores_records = []
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
                "split": "calibration",
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

    # 4. Champion manifest
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

    return run_dir, feat_path


def test_package_rejects_infeasible_or_missing_champion(tmp_path: Path) -> None:
    run_dir = tmp_path / "infeasible_run"
    run_dir.mkdir()
    (run_dir / "champion-manifest.json").write_text(
        json.dumps({"schema_version": "phase1b-champion-v1", "verdict": "NOT FEASIBLE"}),
        encoding="utf-8",
    )
    with pytest.raises(ChampionPackageError, match="FEASIBLE champion"):
        build_champion_package(run_dir, tmp_path / "features.parquet", tmp_path / "pkg")


def test_package_rejects_any_referenced_hash_mismatch(tmp_path: Path) -> None:
    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    # Tamper with model binary
    (run_dir / "models" / "statistical.joblib").write_bytes(b"tampered_bytes")
    with pytest.raises(ChampionPackageError, match="missing or SHA-256 mismatch"):
        build_champion_package(run_dir, feat_path, tmp_path / "pkg")


def test_package_contains_one_model_and_three_golden_cases(tmp_path: Path) -> None:
    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    pkg_dir = tmp_path / "pkg"
    result = build_champion_package(run_dir, feat_path, pkg_dir)

    assert result.output_dir.exists()
    assert result.manifest.schema_version == "champion-package-v1"
    assert result.manifest.model_id == "statistical"
    assert result.manifest.golden_case_count == 3

    assert (pkg_dir / "manifest.json").exists()
    assert (pkg_dir / "detector.joblib").exists()
    assert (pkg_dir / "evidence-baseline.npz").exists()
    assert (pkg_dir / "golden-cases.json").exists()

    golden_json = json.loads((pkg_dir / "golden-cases.json").read_text(encoding="utf-8"))
    assert golden_json["schema_version"] == "champion-golden-cases-v1"
    assert len(golden_json["cases"]) == 3


def test_package_manifest_validates_role_combinations() -> None:
    from industrial_reliability.package_champion import ChampionManifest, ThresholdProvenance

    valid_hashes = {
        "detector.joblib": "a" * 64,
        "evidence-baseline.npz": "b" * 64,
        "golden-cases.json": "c" * 64,
    }

    # Valid CHAMPION
    m_champ = ChampionManifest(
        schema_version="champion-package-v1",
        package_role="CHAMPION",
        evaluation_verdict="FEASIBLE",
        operational_status="PRODUCTION_CANDIDATE",
        source_champion_schema="phase1b-champion-v1",
        source_run_id="run-1",
        model_id="statistical",
        model_version="v1",
        contract_sha256="d" * 64,
        source_dataset_sha256="e" * 64,
        feature_names=("f1",),
        threshold=1.0,
        threshold_provenance=ThresholdProvenance(),
        artifact_sha256=valid_hashes,
    )
    assert m_champ.package_role == "CHAMPION"

    # Valid RESEARCH_CANDIDATE
    m_res = ChampionManifest(
        schema_version="champion-package-v1",
        package_role="RESEARCH_CANDIDATE",
        evaluation_verdict="NOT_FEASIBLE",
        operational_status="RESEARCH_ONLY",
        source_champion_schema="phase1b-run-v1",
        source_run_id="run-1",
        model_id="statistical",
        model_version="v1",
        contract_sha256="d" * 64,
        source_dataset_sha256="e" * 64,
        feature_names=("f1",),
        threshold=1.0,
        threshold_provenance=ThresholdProvenance(),
        artifact_sha256=valid_hashes,
    )
    assert m_res.package_role == "RESEARCH_CANDIDATE"

    # Invalid combination: CHAMPION with NOT_FEASIBLE
    prov = ThresholdProvenance()
    with pytest.raises(ValueError, match="invalid package role"):
        ChampionManifest(
            schema_version="champion-package-v1",
            package_role="CHAMPION",
            evaluation_verdict="NOT_FEASIBLE",
            operational_status="PRODUCTION_CANDIDATE",
            source_champion_schema="phase1b-champion-v1",
            source_run_id="run-1",
            model_id="statistical",
            model_version="v1",
            contract_sha256="d" * 64,
            source_dataset_sha256="e" * 64,
            feature_names=("f1",),
            threshold=1.0,
            threshold_provenance=prov,
            artifact_sha256=valid_hashes,
        )


def test_build_research_candidate_package(tmp_path: Path) -> None:
    from industrial_reliability.package_research_candidate import build_research_candidate_package

    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    # Convert run_manifest to NOT FEASIBLE phase1b-run-v1
    feat_manifest = tmp_path / "feature_manifest.json"
    feat_manifest.write_text(
        json.dumps(
            {
                "output_sha256": sha256_file(feat_path),
                "active_feature_names": ["tp2_mean", "dv_pressure_mean"],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "phase1b-run-v1",
                "run_id": "phase1b-run-mock",
                "verdict": "NOT FEASIBLE",
                "selected_model": None,
                "contract_sha256": "a" * 64,
                "source_dataset_sha256": "b" * 64,
                "feature_output_sha256": sha256_file(feat_path),
                "models": {
                    "statistical": {
                        "threshold": 1.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "research_pkg"
    res = build_research_candidate_package(
        run_dir=run_dir,
        features_path=feat_path,
        feature_manifest_path=feat_manifest,
        output_dir=out_dir,
    )

    assert res.output_dir.exists()
    assert res.manifest.package_role == "RESEARCH_CANDIDATE"
    assert res.manifest.evaluation_verdict == "NOT_FEASIBLE"
    assert res.manifest.operational_status == "RESEARCH_ONLY"
    assert res.manifest.source_champion_schema == "phase1b-run-v1"
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "alert-policy.json").exists()
    assert (out_dir / "detector.joblib").exists()
    assert (out_dir / "golden-cases.json").exists()
