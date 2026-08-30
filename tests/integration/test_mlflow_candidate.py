from __future__ import annotations

from pathlib import Path

import mlflow
import pytest
from tests.helpers_champion import create_mock_phase1b_champion_run

from industrial_reliability.ml_lifecycle import (
    CandidateResult,
    ImportCandidateRequest,
    ReproductionRequest,
    import_candidate,
    reproduce_candidate,
)

pytest.importorskip("mlflow")


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


@pytest.mark.integration
def test_candidate_run_contains_downloadable_pyfunc(tmp_path: Path) -> None:
    run_dir, _features, package = _setup_test_run(tmp_path)
    tracking_uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    result = import_candidate(ImportCandidateRequest(package, run_dir, tracking_uri=tracking_uri))
    mlflow.set_tracking_uri(tracking_uri)
    downloaded = mlflow.artifacts.download_artifacts(
        artifact_uri=f"runs:/{result.run_id}/champion-model"
    )
    assert Path(downloaded, "MLmodel").is_file()

