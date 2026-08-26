from __future__ import annotations

import json
from pathlib import Path

import pytest

from industrial_reliability.package_champion import (
    ChampionPackageError,
    build_champion_package,
)
from tests.helpers_champion import (
    build_research_candidate_from_mock_run,
    create_mock_phase1b_champion_run,
)


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
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    # Tamper with model binary
    (mock_run.run_dir / "models" / "statistical.joblib").write_bytes(b"tampered_bytes")
    with pytest.raises(ChampionPackageError, match="missing or SHA-256 mismatch"):
        build_champion_package(mock_run.run_dir, mock_run.features_path, tmp_path / "pkg")


def test_package_contains_one_model_and_three_golden_cases(tmp_path: Path) -> None:
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    pkg_dir = tmp_path / "pkg"
    result = build_champion_package(mock_run.run_dir, mock_run.features_path, pkg_dir)

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
    mock = build_research_candidate_from_mock_run(tmp_path)
    res = mock.build_result

    assert res.output_dir.exists()
    assert res.manifest.package_role == "RESEARCH_CANDIDATE"
    assert res.manifest.evaluation_verdict == "NOT_FEASIBLE"
    assert res.manifest.operational_status == "RESEARCH_ONLY"
    assert res.manifest.source_champion_schema == "phase1b-run-v1"
    assert (mock.package_dir / "manifest.json").exists()
    assert (mock.package_dir / "alert-policy.json").exists()
    assert (mock.package_dir / "detector.joblib").exists()
    assert (mock.package_dir / "golden-cases.json").exists()
