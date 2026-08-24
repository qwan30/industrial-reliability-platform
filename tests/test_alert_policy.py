from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from industrial_reliability.alert_policy import (
    lock_alert_policy,
    select_policy,
)
from industrial_reliability.phase1b_data import sha256_file


def _write_champion_fixture(tmp_path: Path, model_id: str = "statistical") -> Path:
    # 1. Write scores.parquet with calibration & holdout rows
    start_ts = datetime(2020, 3, 1, 0, 0, 0)
    rows = []
    # 288 5-min intervals = 1 day of calibration data
    for i in range(288):
        ts = start_ts + timedelta(minutes=5 * i)
        # Sparse anomalies
        is_anom = i in (50, 51, 150)
        rows.append(
            {
                "model_id": model_id,
                "split": "calibration",
                "window_start": ts,
                "window_end": ts + timedelta(minutes=30),
                "score": 1.2 if is_anom else 0.4,
                "threshold": 1.0,
                "is_anomaly": is_anom,
            }
        )
    # Some holdout rows
    for i in range(50):
        ts = start_ts + timedelta(days=10, minutes=5 * i)
        rows.append(
            {
                "model_id": model_id,
                "split": "holdout",
                "window_start": ts,
                "window_end": ts + timedelta(minutes=30),
                "score": 1.5,
                "threshold": 1.0,
                "is_anomaly": True,
            }
        )

    scores_df = pd.DataFrame(rows)
    scores_path = tmp_path / "scores.parquet"
    scores_df.to_parquet(scores_path, index=False)
    scores_sha = sha256_file(scores_path)

    manifest_data = {
        "schema_version": "phase1b-champion-manifest-v1",
        "model_id": model_id,
        "model_version": "champion-statistical-v1",
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "threshold": 1.0,
        "stride_seconds": 300,
        "artifact_sha256": {
            "scores.parquet": scores_sha,
        },
    }
    manifest_path = tmp_path / "champion-manifest.json"
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
    return manifest_path


def test_lock_policy_uses_only_champion_calibration_rows(tmp_path: Path) -> None:
    manifest = _write_champion_fixture(tmp_path, model_id="statistical")
    out_file = tmp_path / "alert-policy.json"
    policy = lock_alert_policy(manifest, out_file)
    assert policy.source_split == "calibration"
    assert policy.model_id == "statistical"
    assert policy.persistence_decisions in (1, 2, 3)
    assert policy.cooldown_decisions in (1, 2, 3, 6)
    assert policy.merge_gap_seconds in (0, 300, 900)
    assert out_file.is_file()

    # Verify deterministic output
    policy2 = lock_alert_policy(manifest, tmp_path / "alert-policy-2.json")
    assert policy.policy_sha256 == policy2.policy_sha256


def test_lock_policy_rejects_score_hash_mismatch(tmp_path: Path) -> None:
    manifest = _write_champion_fixture(tmp_path, model_id="statistical")
    (tmp_path / "scores.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match=r"scores\.parquet"):
        lock_alert_policy(manifest, tmp_path / "alert-policy.json")


def test_candidate_evaluator_rejects_holdout_rows() -> None:
    frame = pd.DataFrame(
        [
            {
                "model_id": "statistical",
                "split": "holdout",
                "window_start": datetime(2020, 3, 1, 0, 0),
                "window_end": datetime(2020, 3, 1, 0, 30),
                "score": 1.2,
                "threshold": 1.0,
                "is_anomaly": True,
            }
        ]
    )
    with pytest.raises(ValueError, match="calibration"):
        select_policy(frame, stride_seconds=300)
