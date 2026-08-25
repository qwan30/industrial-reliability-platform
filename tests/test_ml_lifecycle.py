import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from industrial_reliability import phase1b_benchmark
from industrial_reliability.ml_lifecycle import (
    CandidateResult,
    ImportCandidateRequest,
    PackagedChampionPyFunc,
    PromotionRequest,
    ReproductionRequest,
    import_candidate,
    promote_candidate,
    reproduce_candidate,
)
from industrial_reliability.ml_provenance import PromotionReceiptV1
from industrial_reliability.models import RobustStatisticalDetector
from industrial_reliability.package_champion import build_champion_package
from industrial_reliability.phase1b_data import sha256_file


@dataclass
class FakeRunInfo:
    run_id: str
    experiment_id: str = "exp-1"


@dataclass
class FakeRun:
    info: FakeRunInfo
    data: Any = None


@dataclass
class FakeModelVersion:
    version: str = "1"
    run_id: str = "fake-run-123456"
    status: str = "READY"


class FakeMlflowClient:
    def __init__(self) -> None:
        self.tags: dict[str, dict[str, str]] = {}
        self.params: dict[str, dict[str, Any]] = {}
        self.metrics: dict[str, dict[str, float]] = {}
        self.logged_models: dict[str, Any] = {}
        self.registered_models: list[str] = []
        self.aliases: dict[str, dict[str, str]] = {}
        self.artifacts: dict[str, dict[str, bytes]] = {}
        self.runs: dict[str, FakeRun] = {}
        self.model_versions: dict[str, list[FakeModelVersion]] = {}

    def create_run(self, experiment_id: str, tags: dict[str, str] | None = None) -> FakeRun:
        run_id = f"fake-run-{uuid.uuid4().hex[:12]}"
        run = FakeRun(info=FakeRunInfo(run_id=run_id, experiment_id=experiment_id))
        self.runs[run.info.run_id] = run
        self.tags[run.info.run_id] = dict(tags or {})
        self.params[run.info.run_id] = {}
        self.metrics[run.info.run_id] = {}
        self.artifacts[run.info.run_id] = {}
        return run

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        self.tags.setdefault(run_id, {})[key] = value

    def log_param(self, run_id: str, key: str, value: Any) -> None:
        self.params.setdefault(run_id, {})[key] = value

    def log_metric(self, run_id: str, key: str, value: float) -> None:
        self.metrics.setdefault(run_id, {})[key] = value

    def log_artifact(self, run_id: str, local_path: str, artifact_path: str | None = None) -> None:
        content = Path(local_path).read_bytes()
        name = Path(local_path).name
        if artifact_path:
            name = f"{artifact_path}/{name}"
        self.artifacts.setdefault(run_id, {})[name] = content

    def get_run(self, run_id: str) -> FakeRun:
        if run_id not in self.runs:
            raise ValueError(f"Run {run_id} not found")
        return self.runs[run_id]

    def create_registered_model(self, name: str) -> None:
        if name not in self.registered_models:
            self.registered_models.append(name)

    def create_model_version(self, name: str, source: str, run_id: str) -> FakeModelVersion:
        version = str(len(self.model_versions.get(name, [])) + 1)
        mv = FakeModelVersion(version=version, run_id=run_id)
        self.model_versions.setdefault(name, []).append(mv)
        return mv

    def set_registered_model_alias(self, name: str, alias: str, version: str) -> None:
        self.aliases.setdefault(name, {})[alias] = version

    def get_model_version_by_alias(self, name: str, alias: str) -> FakeModelVersion:
        if name not in self.aliases or alias not in self.aliases[name]:
            raise ValueError(f"Alias {alias} not found for {name}")
        version_str = self.aliases[name][alias]
        for mv in self.model_versions.get(name, []):
            if mv.version == version_str:
                return mv
        return FakeModelVersion(version=version_str, run_id="fake-run-123456")


def _create_mock_feasible_phase1b_run(base_dir: Path) -> tuple[Path, Path, Path]:
    run_dir = base_dir / "run-001"
    run_dir.mkdir(parents=True, exist_ok=True)
    models_dir = run_dir / "models"
    models_dir.mkdir(exist_ok=True)

    feature_names = ["tp2_mean", "dv_pressure_mean"]
    # 1. Fit mock detector
    train_data = np.array([[1.0, 2.0], [1.1, 2.1], [0.9, 1.9]], dtype=np.float64)
    detector = RobustStatisticalDetector().fit(train_data)
    model_path = models_dir / "statistical.joblib"
    joblib.dump(detector, model_path)

    # 2. Evidence baseline
    median = np.median(train_data, axis=0)
    mad = np.median(np.abs(train_data - median), axis=0)
    baseline_path = run_dir / "evidence-baseline.npz"
    np.savez_compressed(
        baseline_path,
        feature_names=np.array(feature_names),
        median=median,
        mad=mad,
    )

    # 3. Features Parquet
    feat_records = []
    scores_records = []
    base_ts = datetime(2020, 2, 25, 0, 0)
    for i in range(10):
        ts_start = base_ts + timedelta(minutes=5 * i)
        ts_end = ts_start + timedelta(minutes=30)
        val_tp2 = 1.0 + i * 0.5
        val_dv = 2.0 + i * 0.5
        feat_vec = np.array([[val_tp2, val_dv]], dtype=np.float64)
        sc = float(detector.score(feat_vec)[0])
        feat_records.append(
            {
                "split": "train" if i < 5 else "calibration",
                "window_start": ts_start,
                "window_end": ts_end,
                "tp2_mean": val_tp2,
                "dv_pressure_mean": val_dv,
            }
        )
        scores_records.append(
            {
                "model_id": "statistical",
                "split": "calibration",
                "window_start": ts_start,
                "window_end": ts_end,
                "score": sc,
                "threshold": 1.0,
                "is_anomaly": sc >= 1.0,
            }
        )

    feat_path = base_dir / "features.parquet"
    feat_table = pa.Table.from_pandas(pd.DataFrame(feat_records), preserve_index=False)
    pq.write_table(feat_table, feat_path, compression="snappy")

    scores_path = run_dir / "scores.parquet"
    scores_table = pa.Table.from_pandas(pd.DataFrame(scores_records), preserve_index=False)
    pq.write_table(scores_table, scores_path, compression="snappy")

    # 4. Champion manifest
    champion_manifest = {
        "schema_version": "phase1b-champion-v1",
        "run_id": "run-001",
        "verdict": "FEASIBLE",
        "model_id": "statistical",
        "model_version": "champion-statistical-v1",
        "threshold": 1.0,
        "threshold_provenance": {
            "split": "calibration",
            "quantile": 0.995,
            "method": "higher",
        },
        "active_feature_names": feature_names,
        "contract_sha256": "a" * 64,
        "source_dataset_sha256": "b" * 64,
        "feature_output_sha256": sha256_file(feat_path),
        "artifact_sha256": {
            "scores_parquet": sha256_file(scores_path),
            "model_binary": sha256_file(model_path),
            "evidence_baseline": sha256_file(baseline_path),
        },
    }
    (run_dir / "champion-manifest.json").write_text(
        json.dumps(champion_manifest, indent=2), encoding="utf-8"
    )

    pkg_dir = base_dir / "champion"
    build_champion_package(run_dir, feat_path, pkg_dir)

    return run_dir, feat_path, pkg_dir


def test_packaged_pyfunc_predict() -> None:
    pyfunc = PackagedChampionPyFunc()
    mock_champion = Mock()
    mock_champion.feature_names = ("feat_a", "feat_b")
    mock_champion.threshold = 0.5
    mock_detector = Mock()
    mock_detector.score = Mock(return_value=np.array([0.2, 0.8]))
    mock_champion.detector = mock_detector
    pyfunc._champion = mock_champion

    df_valid = pd.DataFrame({"feat_a": [1.0, 2.0], "feat_b": [3.0, 4.0]})
    res = pyfunc.predict(Mock(), df_valid)
    assert list(res.columns) == ["score", "is_anomaly"]
    assert list(res["is_anomaly"]) == [False, True]

    df_invalid = pd.DataFrame({"feat_b": [3.0, 4.0], "feat_a": [1.0, 2.0]})
    with pytest.raises(ValueError, match="feature names/order"):
        pyfunc.predict(Mock(), df_invalid)


def test_import_candidate_stops_at_candidate(tmp_path: Path) -> None:
    run_dir, _feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    req = ImportCandidateRequest(
        champion_package=pkg_dir,
        phase1b_run_dir=run_dir,
        expected_source_git_sha=None,
    )
    result = import_candidate(req, mlflow_client=fake_client)
    assert isinstance(result, CandidateResult)
    assert fake_client.tags[result.run_id]["lifecycle_state"] == "candidate"
    assert fake_client.registered_models == []
    assert fake_client.aliases == {}


def test_reproduction_never_evaluates_holdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        phase1b_benchmark,
        "run_phase1b_benchmark",
        Mock(side_effect=AssertionError("Holdout evaluated!")),
    )
    run_dir, feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    req = ReproductionRequest(
        features_path=feat_path,
        phase1b_run_dir=run_dir,
        champion_package=pkg_dir,
        expected_source_git_sha=None,
    )
    res = reproduce_candidate(req, mlflow_client=fake_client)
    assert fake_client.tags[res.run_id]["lifecycle_state"] == "reproduction"
    assert isinstance(res.threshold, float)
    assert len(res.calibration_scores) > 0
    assert len(res.golden_scores) > 0


def test_promote_candidate_verifies_and_registers(tmp_path: Path) -> None:
    run_dir, _feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    req_import = ImportCandidateRequest(
        champion_package=pkg_dir,
        phase1b_run_dir=run_dir,
    )
    import_res = import_candidate(req_import, mlflow_client=fake_client)

    out_receipt = tmp_path / "promotion-receipt.json"
    req_promote = PromotionRequest(
        run_id=import_res.run_id,
        approver="reliability-lead",
        expected_source_git_sha=import_res.provenance.source_git_sha,
        output=out_receipt,
        champion_package=pkg_dir,
    )
    receipt = promote_candidate(req_promote, mlflow_client=fake_client)
    assert isinstance(receipt, PromotionReceiptV1)
    assert receipt.alias == "champion"
    assert receipt.approver == "reliability-lead"
    assert out_receipt.exists()
    assert fake_client.aliases["industrial-reliability-anomaly-detector"]["champion"] == "1"


def test_promote_candidate_rejects_empty_approver(tmp_path: Path) -> None:
    fake_client = FakeMlflowClient()
    req = PromotionRequest(
        run_id="fake-run",
        approver="",
        expected_source_git_sha="d" * 40,
        output=tmp_path / "receipt.json",
    )
    with pytest.raises(ValueError, match="approver"):
        promote_candidate(req, mlflow_client=fake_client)


def test_import_candidate_missing_manifest(tmp_path: Path) -> None:
    fake_client = FakeMlflowClient()
    req = ImportCandidateRequest(
        champion_package=tmp_path / "nonexistent",
        phase1b_run_dir=tmp_path,
    )
    with pytest.raises(FileNotFoundError, match="manifest not found"):
        import_candidate(req, mlflow_client=fake_client)


def test_import_candidate_git_sha_mismatch(tmp_path: Path) -> None:
    run_dir, _feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    req = ImportCandidateRequest(
        champion_package=pkg_dir,
        phase1b_run_dir=run_dir,
        expected_source_git_sha="f" * 40,
    )
    with pytest.raises(ValueError, match="Source Git SHA mismatch"):
        import_candidate(req, mlflow_client=fake_client)


def test_reproduce_candidate_missing_manifest(tmp_path: Path) -> None:
    fake_client = FakeMlflowClient()
    req = ReproductionRequest(
        features_path=tmp_path / "features.parquet",
        phase1b_run_dir=tmp_path,
        champion_package=tmp_path / "nonexistent",
    )
    with pytest.raises(FileNotFoundError, match="manifest not found"):
        reproduce_candidate(req, mlflow_client=fake_client)


def test_reproduce_candidate_git_sha_mismatch(tmp_path: Path) -> None:
    run_dir, feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    req = ReproductionRequest(
        features_path=feat_path,
        phase1b_run_dir=run_dir,
        champion_package=pkg_dir,
        expected_source_git_sha="f" * 40,
    )
    with pytest.raises(ValueError, match="Source Git SHA mismatch"):
        reproduce_candidate(req, mlflow_client=fake_client)


def test_promote_candidate_invalid_lifecycle_state(tmp_path: Path) -> None:
    fake_client = FakeMlflowClient()
    run = fake_client.create_run(experiment_id="exp-1")
    fake_client.set_tag(run.info.run_id, "lifecycle_state", "reproduction")
    req = PromotionRequest(
        run_id=run.info.run_id,
        approver="lead",
        expected_source_git_sha="0" * 40,
        output=tmp_path / "receipt.json",
    )
    with pytest.raises(ValueError, match="Cannot promote run"):
        promote_candidate(req, mlflow_client=fake_client)


def test_pyfunc_load_context(tmp_path: Path) -> None:
    _run_dir, _feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    pyfunc = PackagedChampionPyFunc()
    context = Mock()
    context.artifacts = {"champion_package": str(pkg_dir)}
    pyfunc.load_context(context)
    assert pyfunc._champion is not None
    assert list(pyfunc._champion.feature_names) == ["tp2_mean", "dv_pressure_mean"]


def test_cli_main_subcommands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from industrial_reliability.ml_lifecycle import main

    run_dir, feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()

    monkeypatch.setattr(
        "industrial_reliability.ml_lifecycle.mlflow",
        fake_client,
    )
    monkeypatch.setattr(
        "industrial_reliability.ml_lifecycle.MlflowClient",
        lambda tracking_uri=None: fake_client,
    )

    # Test import-candidate
    ret_import = main(
        [
            "import-candidate",
            "--champion-package",
            str(pkg_dir),
            "--phase1b-run-dir",
            str(run_dir),
        ]
    )
    assert ret_import == 0

    # Test reproduce
    ret_repro = main(
        [
            "reproduce",
            "--features-path",
            str(feat_path),
            "--phase1b-run-dir",
            str(run_dir),
            "--champion-package",
            str(pkg_dir),
        ]
    )
    assert ret_repro == 0

    # Test promote
    candidate_runs = [
        rid for rid, tags in fake_client.tags.items() if tags.get("lifecycle_state") == "candidate"
    ]
    run_id = candidate_runs[0]
    out_receipt = tmp_path / "cli_receipt.json"
    ret_promote = main(
        [
            "promote",
            "--run-id",
            run_id,
            "--approver",
            "lead-engineer",
            "--expected-source-git-sha",
            "0" * 40,
            "--output",
            str(out_receipt),
            "--champion-package",
            str(pkg_dir),
        ]
    )
    assert ret_promote == 0
    assert out_receipt.exists()
