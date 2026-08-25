from __future__ import annotations

from pathlib import Path

import pytest

from industrial_reliability.ml_lifecycle import CandidateResult, ReproductionResult
from industrial_reliability.ml_provenance import PromotionReceiptV1, RunProvenanceV1
from industrial_reliability.phase7_gate import (
    Phase7GateResult,
    evaluate_phase7_gate,
    main,
)


def _create_mock_provenance(run_id: str, state: str) -> RunProvenanceV1:
    return RunProvenanceV1(
        schema_version="mlflow-run-provenance-v1",
        mlflow_run_id=run_id,
        experiment_name="industrial-reliability-offline",
        lifecycle_state=state,
        dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        feature_schema_sha256="c" * 64,
        source_git_sha="0" * 40,
        python_version="3.12.0",
        dependency_versions={"numpy": "2.0.0"},
        champion_package_sha256="d" * 64,
        alert_policy_sha256="e" * 64,
        parameters={"model_id": "statistical"},
        metrics={"threshold": 1.23456789},
        artifact_sha256={"manifest.json": "d" * 64},
        provenance_sha256="",
    ).with_computed_hash()


def _create_mock_receipt(run_id: str) -> PromotionReceiptV1:
    return PromotionReceiptV1(
        schema_version="mlflow-promotion-receipt-v1",
        mlflow_run_id=run_id,
        registered_model_name="industrial-reliability-anomaly-detector",
        registered_model_version="1",
        alias="champion",
        model_version="champion-statistical-v1",
        dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        champion_package_sha256="d" * 64,
        source_git_sha="0" * 40,
        approver="lead-engineer",
        promoted_at="2026-08-25T00:00:00Z",
        receipt_sha256="",
    ).with_computed_hash()


def test_evaluate_phase7_gate_pass() -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate")
    repro_prov = _create_mock_provenance("run-002", "reproduction")
    receipt = _create_mock_receipt("run-001")

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
        receipt=receipt,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert isinstance(gate, Phase7GateResult)
    assert gate.verdict == "PASS"
    assert gate.threshold_delta <= 1e-9
    assert gate.golden_scores_max_delta <= 1e-6


def test_evaluate_phase7_gate_fails_on_threshold_delta() -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate")
    repro_prov = _create_mock_provenance("run-002", "reproduction")
    receipt = _create_mock_receipt("run-001")

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
        receipt=receipt,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert gate.verdict == "FAIL"
    assert gate.threshold_delta > 1e-9


def test_evaluate_phase7_gate_fails_on_hash_mismatch() -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate")
    repro_prov = _create_mock_provenance("run-002", "reproduction")
    # Tamper receipt dataset sha
    receipt = PromotionReceiptV1(
        schema_version="mlflow-promotion-receipt-v1",
        mlflow_run_id="run-001",
        registered_model_name="industrial-reliability-anomaly-detector",
        registered_model_version="1",
        alias="champion",
        model_version="champion-statistical-v1",
        dataset_sha256="f" * 64,  # Mismatches candidate
        contract_sha256="b" * 64,
        champion_package_sha256="d" * 64,
        source_git_sha="0" * 40,
        approver="lead-engineer",
        promoted_at="2026-08-25T00:00:00Z",
        receipt_sha256="",
    ).with_computed_hash()

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
        receipt=receipt,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert gate.verdict == "FAIL"


def test_evaluate_phase7_gate_fails_on_lifecycle_state() -> None:
    candidate_prov = _create_mock_provenance("run-001", "reproduction")  # Should be candidate
    repro_prov = _create_mock_provenance("run-002", "candidate")  # Should be reproduction
    receipt = _create_mock_receipt("run-001")

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
        receipt=receipt,
        expected_threshold=1.23456789,
        expected_golden_scores=(0.2, 0.6, 1.0),
    )

    assert gate.verdict == "FAIL"
    assert any("lifecycle_state" in r for r in gate.reasons)


def test_evaluate_phase7_gate_fails_on_golden_scores_delta_and_count() -> None:
    candidate_prov = _create_mock_provenance("run-001", "candidate")
    repro_prov = _create_mock_provenance("run-002", "reproduction")
    receipt = _create_mock_receipt("run-001")

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
        receipt=receipt,
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
        receipt=receipt,
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
        reasons=[],
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
