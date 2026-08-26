from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mlflow")

from tests.helpers_champion import create_mock_phase1b_champion_run

from industrial_reliability.ml_lifecycle import (
    ImportCandidateRequest,
    PromotionRequest,
    import_candidate,
    promote_candidate,
)
from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    load_promotion_receipt,
    verify_promotion_receipt,
)


def _setup_test_run(base_dir: Path) -> tuple[Path, Path, Path]:
    mock_run = create_mock_phase1b_champion_run(base_dir)
    return mock_run.run_dir, mock_run.features_path, mock_run.package_dir


def test_promote_candidate_sqlite_tracking(tmp_path: Path) -> None:
    db_path = tmp_path / "mlflow.db"
    tracking_uri = f"sqlite:///{db_path.as_posix()}"
    run_dir, _feat_path, pkg_dir = _setup_test_run(tmp_path)

    # 1. Import candidate
    import_req = ImportCandidateRequest(
        champion_package=pkg_dir,
        phase1b_run_dir=run_dir,
        tracking_uri=tracking_uri,
    )
    import_res = import_candidate(import_req)

    # 2. Promote candidate
    receipt_out = tmp_path / "promotion-receipt.json"
    promote_req = PromotionRequest(
        run_id=import_res.run_id,
        approver="lead-engineer",
        expected_source_git_sha=import_res.provenance.source_git_sha,
        output=receipt_out,
        champion_package=pkg_dir,
        tracking_uri=tracking_uri,
    )
    receipt = promote_candidate(promote_req)
    assert isinstance(receipt, PromotionReceiptV1)
    assert receipt_out.is_file()

    # 3. Verify receipt verification
    loaded_receipt = load_promotion_receipt(receipt_out)
    assert loaded_receipt.mlflow_run_id == import_res.run_id
    verify_promotion_receipt(loaded_receipt)
