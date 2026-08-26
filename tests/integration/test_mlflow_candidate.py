from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mlflow")

from tests.helpers_champion import create_mock_phase1b_champion_run

from industrial_reliability.ml_lifecycle import (
    CandidateResult,
    ImportCandidateRequest,
    ReproductionRequest,
    import_candidate,
    reproduce_candidate,
)


def _setup_test_run(base_dir: Path) -> tuple[Path, Path, Path]:
    mock_run = create_mock_phase1b_champion_run(base_dir)
    return mock_run.run_dir, mock_run.features_path, mock_run.package_dir


def test_import_and_reproduce_candidate_sqlite_tracking(tmp_path: Path) -> None:
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
    assert isinstance(import_res, CandidateResult)
    assert import_res.provenance.lifecycle_state == "candidate"

    # 2. Reproduce candidate
    repro_req = ReproductionRequest(
        features_path=feat_path,
        phase1b_run_dir=run_dir,
        champion_package=pkg_dir,
        tracking_uri=tracking_uri,
    )
    repro_res = reproduce_candidate(repro_req)
    assert repro_res.provenance.lifecycle_state == "reproduction"
    assert isinstance(repro_res.threshold, float)
