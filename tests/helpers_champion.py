"""Shared builders for mock Phase 1B champion runs and research-candidate packages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from industrial_reliability.models import RobustStatisticalDetector
from industrial_reliability.package_champion import build_champion_package
from industrial_reliability.package_research_candidate import (
    build_research_candidate_package,
)
from industrial_reliability.phase1b_data import sha256_file

_MOCK_FEATURE_NAMES = ["tp2_mean", "dv_pressure_mean"]


@dataclass(frozen=True)
class MockChampionRun:
    """Paths and trust anchor of a fully built mock Phase 1B champion run."""

    run_dir: Path
    features_path: Path
    package_dir: Path
    manifest_sha256: str


@dataclass(frozen=True)
class MockResearchCandidateRun:
    """Paths and build result of a mock research-candidate package."""

    run_dir: Path
    features_path: Path
    package_dir: Path
    manifest_sha256: str
    build_result: Any


def create_mock_phase1b_champion_run(base_dir: Path) -> MockChampionRun:
    """Create a feasible mock Phase 1B run and its champion package.

    Builds the detector binary, evidence baseline, features/scores Parquet
    files, the champion manifest, and a champion package under
    ``base_dir/"champion"``.
    """
    run_dir = base_dir / "run-001"
    run_dir.mkdir(parents=True, exist_ok=True)
    models_dir = run_dir / "models"
    models_dir.mkdir(exist_ok=True)

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
        feature_names=np.array(_MOCK_FEATURE_NAMES),
        median=median,
        mad=mad,
    )

    # 3. Features and scores Parquet
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
        "active_feature_names": _MOCK_FEATURE_NAMES,
        "contract_sha256": "a" * 64,
        "source_dataset_sha256": "b" * 64,
        "prepared_output_sha256": "c" * 64,
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

    return MockChampionRun(
        run_dir=run_dir,
        features_path=feat_path,
        package_dir=pkg_dir,
        manifest_sha256=sha256_file(pkg_dir / "manifest.json"),
    )


def build_research_candidate_from_mock_run(base_dir: Path) -> MockResearchCandidateRun:
    """Convert a mock champion run into a NOT FEASIBLE research-candidate package.

    Rewrites the run manifest to the ``phase1b-run-v1`` NOT FEASIBLE verdict,
    writes the feature manifest, and builds the research-only candidate
    package under ``base_dir/"research_pkg"``.
    """
    mock_run = create_mock_phase1b_champion_run(base_dir)
    feat_manifest = base_dir / "feature_manifest.json"
    feat_manifest.write_text(
        json.dumps(
            {
                "output_sha256": sha256_file(mock_run.features_path),
                "active_feature_names": _MOCK_FEATURE_NAMES,
            }
        ),
        encoding="utf-8",
    )
    (mock_run.run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "phase1b-run-v1",
                "run_id": "phase1b-run-mock",
                "verdict": "NOT FEASIBLE",
                "selected_model": None,
                "contract_sha256": "a" * 64,
                "source_dataset_sha256": "b" * 64,
                "prepared_output_sha256": "c" * 64,
                "feature_output_sha256": sha256_file(mock_run.features_path),
                "models": {
                    "statistical": {
                        "threshold": 1.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    pkg_dir = base_dir / "research_pkg"
    result = build_research_candidate_package(
        run_dir=mock_run.run_dir,
        features_path=mock_run.features_path,
        feature_manifest_path=feat_manifest,
        output_dir=pkg_dir,
    )

    return MockResearchCandidateRun(
        run_dir=mock_run.run_dir,
        features_path=mock_run.features_path,
        package_dir=pkg_dir,
        manifest_sha256=result.manifest_sha256,
        build_result=result,
    )
