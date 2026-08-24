from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from industrial_reliability.champion import (
    ChampionIntegrityError,
    ChampionScorer,
    ScoringContractError,
    load_champion,
)
from industrial_reliability.package_champion import (
    build_champion_package,
)
from industrial_reliability.runtime_messages import (
    CoverageEvidenceV1,
    FeatureVectorV1,
)
from tests.test_package_champion import _create_mock_feasible_phase1b_run


def _make_feature_vector(
    contract_sha: str,
    dataset_sha: str,
    feature_names: tuple[str, ...],
    feature_values: tuple[float, ...],
) -> FeatureVectorV1:
    return FeatureVectorV1(
        schema_version="feature-vector-v1",
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256=dataset_sha,
        contract_sha256=contract_sha,
        source_timestamp=datetime(2020, 2, 25, 0, 30),
        emitted_at=datetime.now(UTC),
        window_id=uuid4(),
        machine_id="compressor-01",
        window_start=datetime(2020, 2, 25, 0, 0),
        window_end=datetime(2020, 2, 25, 0, 30),
        feature_names=feature_names,
        feature_values=feature_values,
        coverage=CoverageEvidenceV1(
            observations_by_bin=(30, 30, 30, 30, 30, 30),
            bin_ends=(
                datetime(2020, 2, 25, 0, 5),
                datetime(2020, 2, 25, 0, 10),
                datetime(2020, 2, 25, 0, 15),
                datetime(2020, 2, 25, 0, 20),
                datetime(2020, 2, 25, 0, 25),
                datetime(2020, 2, 25, 0, 30),
            ),
        ),
    )


def golden_case_to_feature_vector(case: dict[str, Any], scorer: ChampionScorer) -> FeatureVectorV1:
    w_start = datetime.fromisoformat(case["window_start"])
    w_end = datetime.fromisoformat(case["window_end"])
    step = (w_end - w_start) / 6
    bin_ends = (
        w_start + step * 1,
        w_start + step * 2,
        w_start + step * 3,
        w_start + step * 4,
        w_start + step * 5,
        w_end,
    )
    return FeatureVectorV1(
        schema_version="feature-vector-v1",
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256=scorer.source_dataset_sha256,
        contract_sha256=scorer.contract_sha256,
        source_timestamp=w_end,
        emitted_at=datetime.now(UTC),
        window_id=uuid4(),
        machine_id="compressor-01",
        window_start=w_start,
        window_end=w_end,
        feature_names=tuple(case["feature_names"]),
        feature_values=tuple(case["feature_values"]),
        coverage=CoverageEvidenceV1(
            observations_by_bin=(30, 30, 30, 30, 30, 30),
            bin_ends=bin_ends,
        ),
    )


def test_load_champion_rejects_manifest_or_model_tamper(tmp_path: Path) -> None:
    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    pkg_dir = tmp_path / "pkg"
    build_result = build_champion_package(run_dir, feat_path, pkg_dir)
    trust_anchor = build_result.manifest_sha256

    # Test invalid trust anchor
    with pytest.raises(ChampionIntegrityError, match="manifest SHA-256 mismatch"):
        load_champion(pkg_dir, "f" * 64)

    # Test model tamper
    (pkg_dir / "detector.joblib").write_bytes(b"tampered_data")
    with pytest.raises(ChampionIntegrityError, match=r"detector\.joblib SHA-256 mismatch"):
        load_champion(pkg_dir, trust_anchor)


def test_score_rejects_contract_model_and_feature_order(tmp_path: Path) -> None:
    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    pkg_dir = tmp_path / "pkg"
    build_result = build_champion_package(run_dir, feat_path, pkg_dir)
    scorer = load_champion(pkg_dir, build_result.manifest_sha256)

    # Reversed feature order
    reversed_names = tuple(reversed(scorer.feature_names))
    reversed_vals = (1.0, 2.0)
    fv_bad_order = _make_feature_vector(
        scorer.contract_sha256, scorer.source_dataset_sha256, reversed_names, reversed_vals
    )
    with pytest.raises(ScoringContractError, match="Feature order mismatch"):
        scorer.score(fv_bad_order)

    # Contract mismatch
    fv_bad_contract = _make_feature_vector(
        "c" * 64, scorer.source_dataset_sha256, scorer.feature_names, (1.0, 2.0)
    )
    with pytest.raises(ScoringContractError, match="Contract mismatch"):
        scorer.score(fv_bad_contract)


def test_all_golden_cases_match_package(tmp_path: Path) -> None:
    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    pkg_dir = tmp_path / "pkg"
    build_result = build_champion_package(run_dir, feat_path, pkg_dir)
    scorer = load_champion(pkg_dir, build_result.manifest_sha256)

    golden_data = json.loads((pkg_dir / "golden-cases.json").read_text(encoding="utf-8"))
    for case in golden_data["cases"]:
        fv = golden_case_to_feature_vector(case, scorer)
        scored = scorer.score(fv)
        assert scored.score == pytest.approx(case["expected_score"], abs=1e-9)
        assert scored.is_anomaly == case["expected_is_anomaly"]
        assert len(scored.evidence_vector) == len(case["expected_evidence"])
