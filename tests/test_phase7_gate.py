from __future__ import annotations

import json
from pathlib import Path

import pytest

from industrial_reliability.ml_lifecycle import CandidateResult, ReproductionResult
from industrial_reliability.ml_provenance import RunProvenanceV1, canonical_dumps
from industrial_reliability.phase7_gate import (
    Phase7GateResult,
    evaluate_phase7_gate,
    load_phase7_attestation,
    main,
    write_phase7_gate_report,
)


def _create_mock_provenance(
    run_id: str,
    state: str,
    *,
    dataset_sha256: str = "a" * 64,
    contract_sha256: str = "b" * 64,
    feature_schema_sha256: str = "c" * 64,
    champion_package_sha256: str = "d" * 64,
    alert_policy_sha256: str = "e" * 64,
    source_git_sha: str = "0" * 40,
) -> RunProvenanceV1:
    return RunProvenanceV1(
        schema_version="mlflow-run-provenance-v1",
        mlflow_run_id=run_id,
        experiment_name="industrial-reliability-offline",
        lifecycle_state=state,
        dataset_sha256=dataset_sha256,
        contract_sha256=contract_sha256,
        feature_schema_sha256=feature_schema_sha256,
        source_git_sha=source_git_sha,
        python_version="3.12.0",
        dependency_versions={"numpy": "2.0.0"},
        champion_package_sha256=champion_package_sha256,
        alert_policy_sha256=alert_policy_sha256,
        parameters={"model_id": "statistical"},
        metrics={"threshold": 1.23456789},
        artifact_sha256={"manifest.json": champion_package_sha256},
        provenance_sha256="",
    ).with_computed_hash()


def test_phase7_gate_result_hash_and_load(tmp_path: Path) -> None:
    gate = Phase7GateResult(
        schema_version="phase7-gate-v1",
        source_git_sha="0" * 40,
        timestamp="2026-08-25T00:00:00Z",
        verdict="PASS",
        threshold_delta=0.0,
        golden_scores_max_delta=0.0,
        candidate_run_id="cand-001",
        reproduction_run_id="repro-001",
        verified_hashes={
            "dataset_sha256": "a" * 64,
            "contract_sha256": "b" * 64,
            "feature_schema_sha256": "c" * 64,
            "source_git_sha": "0" * 40,
            "champion_package_sha256": "d" * 64,
            "alert_policy_sha256": "e" * 64,
        },
        package_manifest_sha256="d" * 64,
        alert_policy_sha256="e" * 64,
        reasons=[],
        self_sha256="",
    )

    # Test compute_hash and with_computed_hash
    computed = gate.compute_hash()
    assert isinstance(computed, str) and len(computed) == 64
    gate_with_hash = gate.with_computed_hash()
    assert gate_with_hash.self_sha256 == computed

    # Write report and load attestation
    out_file = tmp_path / "phase7-gate.json"
    write_phase7_gate_report(out_file, gate_with_hash)
    loaded = load_phase7_attestation(out_file)
    assert loaded.verdict == "PASS"
    assert loaded.self_sha256 == computed
    assert loaded.package_manifest_sha256 == "d" * 64
    assert loaded.alert_policy_sha256 == "e" * 64

    # Tampered file should fail verification on load
    raw = json.loads(out_file.read_text(encoding="utf-8"))
    raw["verdict"] = "FAIL"
    tampered_file = tmp_path / "tampered-gate.json"
    tampered_file.write_text(canonical_dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="attestation hash mismatch"):
        load_phase7_attestation(tampered_file)


def test_evaluate_phase7_gate_pass() -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate")
    repro_prov = _create_mock_provenance("run-002", "reproduction")

    candidate_res = CandidateResult(
        run_id="run-001",
        model_uri="runs:/run-001/champion-model",
        package_manifest_sha256="d" * 64,
        provenance=candidate_prov,
    )

    repro_res = ReproductionResult(
        run_id="run-002",
        threshold=1.23456789,
        calibration_scores=(0.1, 0.5, 0.9),
        golden_scores=(0.2, 0.6, 1.0),
        provenance=repro_prov,
    )

    gate = evaluate_phase7_gate(
        candidate=candidate_res,
        reproduction=repro_res,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert isinstance(gate, Phase7GateResult)
    assert gate.verdict == "PASS"
    assert gate.threshold_delta <= 1e-9
    assert gate.golden_scores_max_delta <= 1e-6
    assert gate.package_manifest_sha256 == "d" * 64
    assert gate.alert_policy_sha256 == "e" * 64
    assert gate.self_sha256 == gate.compute_hash()


def test_evaluate_phase7_gate_fails_on_threshold_delta() -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate")
    repro_prov = _create_mock_provenance("run-002", "reproduction")

    candidate_res = CandidateResult(
        run_id="run-001",
        model_uri="runs:/run-001/champion-model",
        package_manifest_sha256="d" * 64,
        provenance=candidate_prov,
    )

    repro_res = ReproductionResult(
        run_id="run-002",
        threshold=1.25000000,  # Diverges by 0.015 > 1e-9
        calibration_scores=(0.1, 0.5, 0.9),
        golden_scores=(0.2, 0.6, 1.0),
        provenance=repro_prov,
    )

    gate = evaluate_phase7_gate(
        candidate=candidate_res,
        reproduction=repro_res,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert gate.verdict == "FAIL"
    assert gate.threshold_delta > 1e-9


@pytest.mark.parametrize(
    "mismatch_kwarg",
    [
        {"dataset_sha256": "f" * 64},
        {"contract_sha256": "f" * 64},
        {"feature_schema_sha256": "f" * 64},
        {"champion_package_sha256": "f" * 64},
        {"alert_policy_sha256": "f" * 64},
        {"source_git_sha": "1" * 40},
    ],
)
def test_evaluate_phase7_gate_fails_on_hash_mismatch(mismatch_kwarg: dict[str, str]) -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate")
    repro_prov = _create_mock_provenance("run-002", "reproduction", **mismatch_kwarg)

    candidate_res = CandidateResult(
        run_id="run-001",
        model_uri="runs:/run-001/champion-model",
        package_manifest_sha256="d" * 64,
        provenance=candidate_prov,
    )

    repro_res = ReproductionResult(
        run_id="run-002",
        threshold=1.23456789,
        calibration_scores=(0.1, 0.5, 0.9),
        golden_scores=(0.2, 0.6, 1.0),
        provenance=repro_prov,
    )

    gate = evaluate_phase7_gate(
        candidate=candidate_res,
        reproduction=repro_res,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert gate.verdict == "FAIL"
    assert len(gate.reasons) > 0


def test_evaluate_phase7_gate_fails_on_candidate_package_manifest_mismatch() -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate", champion_package_sha256="d" * 64)
    repro_prov = _create_mock_provenance("run-002", "reproduction", champion_package_sha256="d" * 64)

    candidate_res = CandidateResult(
        run_id="run-001",
        model_uri="runs:/run-001/champion-model",
        package_manifest_sha256="f" * 64,  # Mismatches candidate provenance
        provenance=candidate_prov,
    )

    repro_res = ReproductionResult(
        run_id="run-002",
        threshold=1.23456789,
        calibration_scores=(0.1, 0.5, 0.9),
        golden_scores=(0.2, 0.6, 1.0),
        provenance=repro_prov,
    )

    gate = evaluate_phase7_gate(
        candidate=candidate_res,
        reproduction=repro_res,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert gate.verdict == "FAIL"
    assert any("Package manifest SHA-256 mismatch" in r for r in gate.reasons)


def test_evaluate_phase7_gate_fails_on_lifecycle_state() -> None:
    candidate_prov = _create_mock_provenance("run-001", "reproduction")  # Should be candidate
    repro_prov = _create_mock_provenance("run-002", "candidate")  # Should be reproduction

    candidate_res = CandidateResult(
        run_id="run-001",
        model_uri="runs:/run-001/champion-model",
        package_manifest_sha256="d" * 64,
        provenance=candidate_prov,
    )

    repro_res = ReproductionResult(
        run_id="run-002",
        threshold=1.23456789,
        calibration_scores=(0.1, 0.5, 0.9),
        golden_scores=(0.2, 0.6, 1.0),
        provenance=repro_prov,
    )

    gate = evaluate_phase7_gate(
        candidate=candidate_res,
        reproduction=repro_res,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert gate.verdict == "FAIL"
    assert any("lifecycle_state" in r for r in gate.reasons)


def test_evaluate_phase7_gate_fails_on_golden_scores_delta_and_count() -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate")
    repro_prov = _create_mock_provenance("run-002", "reproduction")

    candidate_res = CandidateResult(
        run_id="run-001",
        model_uri="runs:/run-001/champion-model",
        package_manifest_sha256="d" * 64,
        provenance=candidate_prov,
    )

    # Count mismatch
    repro_count_mismatch = ReproductionResult(
        run_id="run-002",
        threshold=1.23456789,
        calibration_scores=(0.1, 0.5, 0.9),
        golden_scores=(0.2,),
        provenance=repro_prov,
    )
    gate_count = evaluate_phase7_gate(
        candidate=candidate_res,
        reproduction=repro_count_mismatch,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )
    assert gate_count.verdict == "FAIL"

    # Score delta > 1e-6
    repro_delta_mismatch = ReproductionResult(
        run_id="run-002",
        threshold=1.23456789,
        calibration_scores=(0.1, 0.5, 0.9),
        golden_scores=(0.2, 0.6001, 1.0),
        provenance=repro_prov,
    )
    gate_delta = evaluate_phase7_gate(
        candidate=candidate_res,
        reproduction=repro_delta_mismatch,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )
    assert gate_delta.verdict == "FAIL"


def test_phase7_gate_cli_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_gate_result = Phase7GateResult(
        schema_version="phase7-gate-v1",
        source_git_sha="0" * 40,
        timestamp="2026-08-25T00:00:00Z",
        verdict="PASS",
        threshold_delta=0.0,
        golden_scores_max_delta=0.0,
        candidate_run_id="run-1",
        reproduction_run_id="run-2",
        verified_hashes={},
        package_manifest_sha256="d" * 64,
        alert_policy_sha256="e" * 64,
        reasons=[],
        self_sha256="f" * 64,
    )

    monkeypatch.setattr(
        "industrial_reliability.phase7_gate.run_phase7_gate",
        lambda **kwargs: mock_gate_result,
    )

    ret = main(
        [
            "--champion-package",
            str(tmp_path / "pkg"),
            "--features-path",
            str(tmp_path / "feat.parquet"),
            "--phase1b-run-dir",
            str(tmp_path / "phase1b"),
        ]
    )
    assert ret == 0
