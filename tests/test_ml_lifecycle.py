from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from industrial_reliability import phase1b_benchmark
from industrial_reliability.artifact_integrity import ArtifactIntegrityError
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
from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    canonical_dumps,
    load_promotion_receipt,
    verify_promotion_receipt,
)
from industrial_reliability.phase7_gate import Phase7GateResult, evaluate_phase7_gate, write_phase7_gate_report
from tests.helpers_champion import (
    build_research_candidate_from_mock_run,
    create_mock_phase1b_champion_run,
)


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
        p = Path(local_path)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(p)
                    name = f"{artifact_path}/{rel.as_posix()}" if artifact_path else rel.as_posix()
                    self.artifacts.setdefault(run_id, {})[name] = f.read_bytes()
        elif p.is_file():
            content = p.read_bytes()
            name = p.name
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
    mock_run = create_mock_phase1b_champion_run(base_dir)
    return mock_run.run_dir, mock_run.features_path, mock_run.package_dir


def _create_mock_gate_attestation_file(
    path: Path,
    candidate_run_id: str,
    *,
    reproduction_run_id: str = "repro-run-001",
    verdict: str = "PASS",
    package_manifest_sha256: str = "d" * 64,
    source_git_sha: str = "0" * 40,
    alert_policy_sha256: str = "e" * 64,
) -> Phase7GateResult:
    gate = Phase7GateResult(
        schema_version="phase7-gate-v1",
        source_git_sha=source_git_sha,
        timestamp="2026-08-25T00:00:00Z",
        verdict=verdict,  # type: ignore
        threshold_delta=0.0,
        golden_scores_max_delta=0.0,
        candidate_run_id=candidate_run_id,
        reproduction_run_id=reproduction_run_id,
        verified_hashes={
            "dataset_sha256": "a" * 64,
            "contract_sha256": "b" * 64,
            "feature_schema_sha256": "c" * 64,
            "source_git_sha": source_git_sha,
            "champion_package_sha256": package_manifest_sha256,
            "alert_policy_sha256": alert_policy_sha256,
        },
        package_manifest_sha256=package_manifest_sha256,
        alert_policy_sha256=alert_policy_sha256,
        reasons=[],
        self_sha256="",
    ).with_computed_hash()
    write_phase7_gate_report(path, gate)
    return gate


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
    run_dir, feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    req_import = ImportCandidateRequest(
        champion_package=pkg_dir,
        phase1b_run_dir=run_dir,
    )
    import_res = import_candidate(req_import, mlflow_client=fake_client)

    req_repro = ReproductionRequest(
        features_path=feat_path,
        phase1b_run_dir=run_dir,
        champion_package=pkg_dir,
    )
    repro_res = reproduce_candidate(req_repro, mlflow_client=fake_client)

    gate_result = evaluate_phase7_gate(
        candidate=import_res,
        reproduction=repro_res,
        expected_threshold=repro_res.threshold,
        expected_golden_scores=repro_res.golden_scores,
    )
    gate_file = tmp_path / "phase7-gate.json"
    write_phase7_gate_report(gate_file, gate_result)

    out_receipt = tmp_path / "promotion-receipt.json"
    req_promote = PromotionRequest(
        run_id=import_res.run_id,
        approver="reliability-lead",
        expected_source_git_sha=import_res.provenance.source_git_sha,
        output=out_receipt,
        champion_package=pkg_dir,
        phase7_gate=gate_file,
    )
    receipt = promote_candidate(req_promote, mlflow_client=fake_client)
    assert isinstance(receipt, PromotionReceiptV1)
    assert receipt.alias == "champion"
    assert receipt.approver == "reliability-lead"
    assert out_receipt.exists()
    assert fake_client.aliases["industrial-reliability-anomaly-detector"]["champion"] == "1"

    loaded_receipt = load_promotion_receipt(out_receipt)
    assert loaded_receipt.mlflow_run_id == import_res.run_id
    verify_promotion_receipt(loaded_receipt)


def test_promote_candidate_rejects_empty_approver(tmp_path: Path) -> None:
    run_dir, _feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    req_import = ImportCandidateRequest(
        champion_package=pkg_dir,
        phase1b_run_dir=run_dir,
    )
    import_res = import_candidate(req_import, mlflow_client=fake_client)

    gate_file = tmp_path / "phase7-gate.json"
    _create_mock_gate_attestation_file(
        gate_file,
        import_res.run_id,
        package_manifest_sha256=import_res.package_manifest_sha256,
        source_git_sha=import_res.provenance.source_git_sha,
    )

    req = PromotionRequest(
        run_id=import_res.run_id,
        approver="",
        expected_source_git_sha=import_res.provenance.source_git_sha,
        output=tmp_path / "receipt.json",
        champion_package=pkg_dir,
        phase7_gate=gate_file,
    )
    with pytest.raises(ValueError, match="approver"):
        promote_candidate(req, mlflow_client=fake_client)
    assert fake_client.registered_models == []
    assert fake_client.model_versions == {}
    assert fake_client.aliases == {}


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


def test_reproduction_rejects_tampered_features(tmp_path: Path) -> None:
    run_dir, feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()

    # Tamper features.parquet
    with feat_path.open("ab") as f:
        f.write(b"CORRUPTED_BYTES")

    req = ReproductionRequest(
        features_path=feat_path,
        phase1b_run_dir=run_dir,
        champion_package=pkg_dir,
    )
    with pytest.raises(ArtifactIntegrityError, match=r"features\.parquet SHA-256 mismatch"):
        reproduce_candidate(req, mlflow_client=fake_client)


def test_promote_candidate_invalid_lifecycle_state(tmp_path: Path) -> None:
    _run_dir, _feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    run = fake_client.create_run(experiment_id="exp-1")
    fake_client.set_tag(run.info.run_id, "lifecycle_state", "reproduction")
    fake_client.set_tag(run.info.run_id, "source_git_sha", "0" * 40)

    gate_file = tmp_path / "phase7-gate.json"
    _create_mock_gate_attestation_file(gate_file, run.info.run_id)

    req = PromotionRequest(
        run_id=run.info.run_id,
        approver="lead",
        expected_source_git_sha="0" * 40,
        output=tmp_path / "receipt.json",
        champion_package=pkg_dir,
        phase7_gate=gate_file,
    )
    with pytest.raises(ValueError, match="Cannot promote run"):
        promote_candidate(req, mlflow_client=fake_client)
    assert fake_client.registered_models == []
    assert fake_client.model_versions == {}
    assert fake_client.aliases == {}


def test_promotion_rejects_research_package_before_mutation(tmp_path: Path) -> None:
    research_run = build_research_candidate_from_mock_run(tmp_path)
    fake_client = FakeMlflowClient()

    # Import research candidate into MLflow
    import_req = ImportCandidateRequest(
        champion_package=research_run.package_dir,
        phase1b_run_dir=research_run.run_dir,
    )
    import_res = import_candidate(import_req, mlflow_client=fake_client)

    gate_file = tmp_path / "gate.json"
    _create_mock_gate_attestation_file(
        gate_file,
        import_res.run_id,
        package_manifest_sha256=research_run.manifest_sha256,
        source_git_sha=import_res.provenance.source_git_sha,
    )

    receipt_out = tmp_path / "receipt.json"
    promote_req = PromotionRequest(
        run_id=import_res.run_id,
        approver="lead-engineer",
        expected_source_git_sha=import_res.provenance.source_git_sha,
        output=receipt_out,
        champion_package=research_run.package_dir,
        phase7_gate=gate_file,
    )

    with pytest.raises(
        ValueError,
        match=r"(package_role must be CHAMPION|evaluation_verdict must be FEASIBLE|operational_status must be PRODUCTION_CANDIDATE)",
    ):
        promote_candidate(promote_req, mlflow_client=fake_client)

    # Registry must NOT have been mutated
    assert fake_client.registered_models == []
    assert fake_client.model_versions == {}
    assert fake_client.aliases == {}
    assert not receipt_out.exists()


@pytest.mark.parametrize(
    "case,expected_exc,match_str",
    [
        ("gate_verdict_fail", ValueError, "Phase 7 gate must PASS before promotion"),
        ("gate_run_id_mismatch", ValueError, "Phase 7 candidate run does not match promotion run"),
        ("package_sha_mismatch", ValueError, "Phase 7 package SHA does not match promotion package"),
        ("git_sha_expected_mismatch", ValueError, "Source Git SHA mismatch"),
        ("git_sha_gate_mismatch", ValueError, "Source Git SHA mismatch"),
        ("receipt_already_exists", FileExistsError, "Refusing to overwrite promotion receipt"),
    ],
)
def test_promotion_preconditions_do_not_mutate_registry(
    tmp_path: Path,
    case: str,
    expected_exc: type[Exception],
    match_str: str,
) -> None:
    run_dir, _feat_path, pkg_dir = _create_mock_feasible_phase1b_run(tmp_path)
    fake_client = FakeMlflowClient()
    import_res = import_candidate(
        ImportCandidateRequest(champion_package=pkg_dir, phase1b_run_dir=run_dir),
        mlflow_client=fake_client,
    )

    run_id = import_res.run_id
    src_sha = import_res.provenance.source_git_sha
    pkg_sha = import_res.package_manifest_sha256

    gate_verdict = "FAIL" if case == "gate_verdict_fail" else "PASS"
    gate_cand_id = "other-run-id" if case == "gate_run_id_mismatch" else run_id
    gate_pkg_sha = "f" * 64 if case == "package_sha_mismatch" else pkg_sha
    gate_src_sha = "1" * 40 if case == "git_sha_gate_mismatch" else src_sha
    exp_src_sha = "2" * 40 if case == "git_sha_expected_mismatch" else src_sha

    gate_file = tmp_path / f"gate_{case}.json"
    _create_mock_gate_attestation_file(
        gate_file,
        gate_cand_id,
        verdict=gate_verdict,
        package_manifest_sha256=gate_pkg_sha,
        source_git_sha=gate_src_sha,
    )

    receipt_out = tmp_path / f"receipt_{case}.json"
    if case == "receipt_already_exists":
        receipt_out.write_text("existing receipt", encoding="utf-8")

    req = PromotionRequest(
        run_id=run_id,
        approver="lead-engineer",
        expected_source_git_sha=exp_src_sha,
        output=receipt_out,
        champion_package=pkg_dir,
        phase7_gate=gate_file,
    )

    with pytest.raises(expected_exc, match=match_str):
        promote_candidate(req, mlflow_client=fake_client)

    # Registry must NOT have been mutated
    assert fake_client.registered_models == []
    assert fake_client.model_versions == {}
    assert fake_client.aliases == {}


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
    git_sha = fake_client.tags[run_id].get("source_git_sha", "0" * 40)
    manifest_sha = fake_client.tags[run_id].get("champion_package_sha256", "d" * 64)

    gate_file = tmp_path / "cli_phase7_gate.json"
    _create_mock_gate_attestation_file(
        gate_file,
        run_id,
        package_manifest_sha256=manifest_sha,
        source_git_sha=git_sha,
    )

    out_receipt = tmp_path / "cli_receipt.json"
    ret_promote = main(
        [
            "promote",
            "--run-id",
            run_id,
            "--approver",
            "lead-engineer",
            "--expected-source-git-sha",
            git_sha,
            "--output",
            str(out_receipt),
            "--champion-package",
            str(pkg_dir),
            "--phase7-gate",
            str(gate_file),
        ]
    )
    assert ret_promote == 0
    assert out_receipt.exists()
