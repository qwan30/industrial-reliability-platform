from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from industrial_reliability.package_champion import (
    BASELINE_FILENAME,
    DETECTOR_FILENAME,
    DRIFT_REFERENCE_FILENAME,
    GOLDEN_CASES_FILENAME,
    ChampionManifest,
    ChampionPackageError,
    ThresholdProvenance,
    build_champion_package,
    verify_package_files,
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
    assert result.manifest.schema_version == "champion-package-v2"
    assert result.manifest.model_id == "statistical"
    assert result.manifest.golden_case_count == 3
    assert result.manifest.prepared_output_sha256 == "c" * 64

    assert (pkg_dir / "manifest.json").exists()
    assert (pkg_dir / "detector.joblib").exists()
    assert (pkg_dir / "evidence-baseline.npz").exists()
    assert (pkg_dir / "golden-cases.json").exists()
    assert (pkg_dir / "drift-reference.json").exists()
    assert "drift-reference.json" in result.manifest.artifact_sha256

    golden_json = json.loads((pkg_dir / "golden-cases.json").read_text(encoding="utf-8"))
    assert golden_json["schema_version"] == "champion-golden-cases-v1"


def test_package_manifest_validates_role_combinations() -> None:
    from industrial_reliability.package_champion import ChampionManifest, ThresholdProvenance

    valid_hashes = {
        "detector.joblib": "a" * 64,
        "evidence-baseline.npz": "b" * 64,
        "golden-cases.json": "c" * 64,
        "drift-reference.json": "d" * 64,
    }

    # Valid CHAMPION
    m_champ = ChampionManifest(
        schema_version="champion-package-v2",
        package_role="CHAMPION",
        evaluation_verdict="FEASIBLE",
        operational_status="PRODUCTION_CANDIDATE",
        source_champion_schema="phase1b-champion-v1",
        source_run_id="run-1",
        model_id="statistical",
        model_version="v1",
        contract_sha256="d" * 64,
        source_dataset_sha256="e" * 64,
        prepared_output_sha256="c" * 64,
        feature_output_sha256="f" * 64,
        feature_names=("f1",),
        threshold=1.0,
        threshold_provenance=ThresholdProvenance(),
        artifact_sha256=valid_hashes,
    )
    assert m_champ.package_role == "CHAMPION"

    # Valid RESEARCH_CANDIDATE
    m_res = ChampionManifest(
        schema_version="champion-package-v2",
        package_role="RESEARCH_CANDIDATE",
        evaluation_verdict="NOT_FEASIBLE",
        operational_status="RESEARCH_ONLY",
        source_champion_schema="phase1b-run-v1",
        source_run_id="run-1",
        model_id="statistical",
        model_version="v1",
        contract_sha256="d" * 64,
        source_dataset_sha256="e" * 64,
        prepared_output_sha256="c" * 64,
        feature_output_sha256="f" * 64,
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
            schema_version="champion-package-v2",
            package_role="CHAMPION",
            evaluation_verdict="NOT_FEASIBLE",
            operational_status="PRODUCTION_CANDIDATE",
            source_champion_schema="phase1b-champion-v1",
            source_run_id="run-1",
            model_id="statistical",
            model_version="v1",
            contract_sha256="d" * 64,
            source_dataset_sha256="e" * 64,
            prepared_output_sha256="c" * 64,
            feature_output_sha256="f" * 64,
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
    assert (mock.package_dir / "drift-reference.json").exists()
    assert "drift-reference.json" in res.manifest.artifact_sha256


def test_v2_manifest_binds_prepared_output() -> None:
    manifest = ChampionManifest(
        schema_version="champion-package-v2",
        source_run_id="phase1b-run-test",
        model_id="statistical",
        model_version="champion-statistical-v1",
        contract_sha256="a" * 64,
        source_dataset_sha256="b" * 64,
        prepared_output_sha256="c" * 64,
        feature_output_sha256="d" * 64,
        feature_names=("tp2_mean",),
        threshold=1.0,
        threshold_provenance=ThresholdProvenance(),
        artifact_sha256={
            DETECTOR_FILENAME: "e" * 64,
            BASELINE_FILENAME: "f" * 64,
            GOLDEN_CASES_FILENAME: "1" * 64,
            DRIFT_REFERENCE_FILENAME: "2" * 64,
        },
    )
    assert manifest.prepared_output_sha256 == "c" * 64


def test_v1_manifest_is_reported_as_stale() -> None:
    legacy_path = Path("artifacts/research-candidate/manifest.json")
    if legacy_path.is_file():
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        if legacy.get("schema_version") == "champion-package-v1":
            with pytest.raises(ValidationError, match="champion-package-v2"):
                ChampionManifest.model_validate(legacy)
    v1_dict = {
        "schema_version": "champion-package-v1",
        "source_run_id": "phase1b-run-test",
        "model_id": "statistical",
        "model_version": "champion-statistical-v1",
        "contract_sha256": "a" * 64,
        "source_dataset_sha256": "b" * 64,
        "feature_output_sha256": "d" * 64,
        "feature_names": ("tp2_mean",),
        "threshold": 1.0,
        "threshold_provenance": {"split": "calibration", "quantile": 0.995, "method": "higher"},
        "golden_case_count": 3,
        "artifact_sha256": {
            DETECTOR_FILENAME: "e" * 64,
            BASELINE_FILENAME: "f" * 64,
            GOLDEN_CASES_FILENAME: "1" * 64,
            DRIFT_REFERENCE_FILENAME: "2" * 64,
        },
    }
    with pytest.raises(ValidationError, match="champion-package-v2"):
        ChampionManifest.model_validate(v1_dict)


def test_verify_package_files_success(tmp_path: Path) -> None:
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    manifest = verify_package_files(mock_run.package_dir)
    assert manifest.schema_version == "champion-package-v2"


def test_verify_package_files_tamper(tmp_path: Path) -> None:
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    (mock_run.package_dir / DETECTOR_FILENAME).write_bytes(b"corrupted")
    with pytest.raises(ChampionPackageError, match=r"detector\.joblib missing or SHA-256 mismatch"):
        verify_package_files(mock_run.package_dir)


def test_package_champion_cli_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from industrial_reliability.package_champion import main

    mock_run = create_mock_phase1b_champion_run(tmp_path)
    code = main(["--verify-package", str(mock_run.package_dir)])
    assert code == 0
    captured = capsys.readouterr()
    assert "champion-package-v2 verified" in captured.out
