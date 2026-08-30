from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mlflow")

from tests.helpers_champion import create_mock_phase1b_champion_run

from industrial_reliability.ml_lifecycle import (
    ImportCandidateRequest,
    PromotionRequest,
    ReproductionRequest,
    import_candidate,
    promote_candidate,
    reproduce_candidate,
)
from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    load_promotion_receipt,
    verify_promotion_receipt,
)
from industrial_reliability.phase7_gate import (
    evaluate_phase7_gate,
    load_phase7_attestation,
    write_phase7_gate_report,
)


def _setup_test_run(base_dir: Path) -> tuple[Path, Path, Path]:
    mock_run = create_mock_phase1b_champion_run(base_dir)
    return mock_run.run_dir, mock_run.features_path, mock_run.package_dir


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

    # 2. Reproduce candidate
    repro_req = ReproductionRequest(
        features_path=feat_path,
        phase1b_run_dir=run_dir,
        champion_package=pkg_dir,
        tracking_uri=tracking_uri,
    )
    repro_res = reproduce_candidate(repro_req)

    # 3. Evaluate Phase 7 Gate (pre-promotion attestation)
    gate_res = evaluate_phase7_gate(
        candidate=import_res,
        reproduction=repro_res,
        expected_threshold=repro_res.threshold,
        expected_golden_scores=repro_res.golden_scores,
    )
    assert gate_res.verdict == "PASS"

    gate_path = tmp_path / "phase7-gate.json"
    write_phase7_gate_report(gate_path, gate_res)
    loaded_gate = load_phase7_attestation(gate_path)
    assert loaded_gate.verdict == "PASS"

    # 4. Promote candidate
    receipt_out = tmp_path / "promotion-receipt.json"
    promote_req = PromotionRequest(
        run_id=import_res.run_id,
        approver="lead-engineer",
        expected_source_git_sha=import_res.provenance.source_git_sha,
        output=receipt_out,
        champion_package=pkg_dir,
        phase7_gate=gate_path,
        tracking_uri=tracking_uri,
    )
    receipt = promote_candidate(promote_req)
    assert isinstance(receipt, PromotionReceiptV1)
    assert receipt_out.is_file()

    # 5. Verify receipt verification
    loaded_receipt = load_promotion_receipt(receipt_out)
    assert loaded_receipt.mlflow_run_id == import_res.run_id
    verify_promotion_receipt(loaded_receipt)


def test_promote_candidate_sqlite_rejects_tampered_tag(tmp_path: Path) -> None:
    db_path = tmp_path / "mlflow.db"
    tracking_uri = f"sqlite:///{db_path.as_posix()}"
    run_dir, feat_path, pkg_dir = _setup_test_run(tmp_path)

    import_req = ImportCandidateRequest(
        champion_package=pkg_dir,
        phase1b_run_dir=run_dir,
        tracking_uri=tracking_uri,
    )
    import_res = import_candidate(import_req)

    repro_req = ReproductionRequest(
        features_path=feat_path,
        phase1b_run_dir=run_dir,
        champion_package=pkg_dir,
        tracking_uri=tracking_uri,
    )
    repro_res = reproduce_candidate(repro_req)

    gate_res = evaluate_phase7_gate(
        candidate=import_res,
        reproduction=repro_res,
        expected_threshold=repro_res.threshold,
        expected_golden_scores=repro_res.golden_scores,
    )
    assert gate_res.verdict == "PASS"

    gate_path = tmp_path / "phase7-gate.json"
    write_phase7_gate_report(gate_path, gate_res)

    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri)
    client.set_tag(import_res.run_id, "dataset_sha256", "f" * 64)

    receipt_out = tmp_path / "promotion-receipt.json"
    promote_req = PromotionRequest(
        run_id=import_res.run_id,
        approver="lead-engineer",
        expected_source_git_sha=import_res.provenance.source_git_sha,
        output=receipt_out,
        champion_package=pkg_dir,
        phase7_gate=gate_path,
        tracking_uri=tracking_uri,
    )
    with pytest.raises(ValueError, match="dataset_sha256 run tag does not match attested identity"):
        promote_candidate(promote_req)
    assert not receipt_out.exists()
