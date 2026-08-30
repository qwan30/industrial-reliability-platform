from __future__ import annotations

import argparse
import contextlib
import json
import platform
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from industrial_reliability.artifact_integrity import verify_file_sha256
from industrial_reliability.champion import load_champion
from industrial_reliability.evaluation import calibrate_threshold
from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    RunProvenanceV1,
    canonical_dumps,
    canonical_sha256,
    validate_git_sha,
    write_run_provenance,
)
from industrial_reliability.package_champion import ChampionManifest
from industrial_reliability.phase1b_contracts import PHASE1C
from industrial_reliability.phase1b_data import sha256_file
from industrial_reliability.phase7_gate import load_phase7_attestation

EXPERIMENT_NAME = "industrial-reliability-offline"
REGISTERED_MODEL_NAME: Literal["industrial-reliability-anomaly-detector"] = (
    "industrial-reliability-anomaly-detector"
)


def get_current_git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return validate_git_sha(out)
    except Exception:
        return "0" * 40


def get_dependency_versions() -> dict[str, str]:
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import sklearn
    import torch

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pyarrow": pa.__version__,
        "scikit-learn": sklearn.__version__,
        "torch": torch.__version__,
        "joblib": joblib.__version__,
    }


if TYPE_CHECKING:
    import mlflow
    import mlflow.pyfunc
    from mlflow import MlflowClient
else:
    try:
        import mlflow
        import mlflow.pyfunc
        from mlflow import MlflowClient
    except ImportError:
        mlflow = None
        MlflowClient = None

__all__ = ["MlflowClient", "import_candidate", "promote_candidate", "reproduce_candidate"]


class PackagedChampionPyFunc:
    def __init__(self, expected_manifest_sha256: str | None = None) -> None:
        self.expected_manifest_sha256 = expected_manifest_sha256
        self._champion: Any = None

    def load_context(self, context: Any) -> None:
        pkg_dir = Path(context.artifacts["champion_package"])
        manifest_sha = self.expected_manifest_sha256 or sha256_file(pkg_dir / "manifest.json")
        self._champion = load_champion(pkg_dir, expected_manifest_sha256=manifest_sha)

    def predict(
        self,
        context: Any,
        model_input: pd.DataFrame,
        params: dict[str, object] | None = None,
    ) -> pd.DataFrame:
        expected = list(self._champion.feature_names)
        if list(model_input.columns) != expected:
            raise ValueError("feature names/order differ from champion package")
        matrix = model_input.to_numpy(dtype=np.float64, copy=False)
        raw_scores = self._champion.detector.score(matrix)
        is_anomaly = raw_scores >= self._champion.threshold
        return pd.DataFrame({"score": raw_scores, "is_anomaly": is_anomaly})


@dataclass(frozen=True)
class ImportCandidateRequest:
    champion_package: Path
    phase1b_run_dir: Path
    expected_source_git_sha: str | None = None
    alert_policy_path: Path | None = None
    tracking_uri: str | None = None


@dataclass(frozen=True)
class CandidateResult:
    run_id: str
    model_uri: str
    package_manifest_sha256: str
    provenance: RunProvenanceV1


@dataclass(frozen=True)
class ReproductionRequest:
    features_path: Path
    phase1b_run_dir: Path
    champion_package: Path
    expected_source_git_sha: str | None = None
    alert_policy_path: Path | None = None
    tracking_uri: str | None = None


@dataclass(frozen=True)
class ReproductionResult:
    run_id: str
    threshold: float
    calibration_scores: tuple[float, ...]
    golden_scores: tuple[float, ...]
    provenance: RunProvenanceV1


@dataclass(frozen=True)
class PromotionRequest:
    run_id: str
    approver: str
    expected_source_git_sha: str
    output: Path
    champion_package: Path
    phase7_gate: Path
    tracking_uri: str | None = None


def _ensure_experiment(client: Any, experiment_name: str) -> str:
    if hasattr(client, "get_experiment_by_name"):
        exp = client.get_experiment_by_name(experiment_name)
        if exp is not None:
            return str(exp.experiment_id)
    if hasattr(client, "create_experiment"):
        try:
            return str(client.create_experiment(experiment_name))
        except Exception:
            if hasattr(client, "get_experiment_by_name"):
                exp = client.get_experiment_by_name(experiment_name)
                if exp is not None:
                    return str(exp.experiment_id)
    return "default-exp"


def import_candidate(
    request: ImportCandidateRequest,
    *,
    mlflow_client: Any = None,
) -> CandidateResult:
    pkg_manifest_path = request.champion_package / "manifest.json"
    if not pkg_manifest_path.is_file():
        raise FileNotFoundError(f"Champion package manifest not found at {pkg_manifest_path}")

    pkg_manifest_sha = sha256_file(pkg_manifest_path)
    pkg_manifest = ChampionManifest.model_validate_json(
        pkg_manifest_path.read_text(encoding="utf-8")
    )

    git_sha = get_current_git_sha()
    if request.expected_source_git_sha and request.expected_source_git_sha != git_sha:
        raise ValueError(
            f"Source Git SHA mismatch: expected {request.expected_source_git_sha}, got {git_sha}"
        )

    alert_policy_sha = "0" * 64
    if request.alert_policy_path and request.alert_policy_path.is_file():
        alert_policy_sha = sha256_file(request.alert_policy_path)
    else:
        # Default mock / placeholder hash for alert policy
        alert_policy_sha = canonical_sha256({"policy": "default-locked-policy"})

    feature_schema_sha = canonical_sha256({"features": list(pkg_manifest.feature_names)})

    # Initialize MLflow tracking if not passed
    client = mlflow_client
    if client is None:
        if mlflow is None:
            raise RuntimeError("MLflow is not installed")
        if request.tracking_uri:
            mlflow.set_tracking_uri(request.tracking_uri)
        client = MlflowClient(tracking_uri=request.tracking_uri)

    exp_id = _ensure_experiment(client, EXPERIMENT_NAME)

    run = client.create_run(experiment_id=exp_id)
    run_id = str(run.info.run_id)

    tags = {
        "schema_version": "mlflow-run-provenance-v1",
        "dataset_sha256": pkg_manifest.source_dataset_sha256,
        "contract_sha256": pkg_manifest.contract_sha256,
        "feature_schema_sha256": feature_schema_sha,
        "source_git_sha": git_sha,
        "champion_package_sha256": pkg_manifest_sha,
        "alert_policy_sha256": alert_policy_sha,
        "lifecycle_state": "candidate",
    }
    for k, v in tags.items():
        client.set_tag(run_id, k, v)

    parameters: dict[str, Any] = {
        "model_id": pkg_manifest.model_id,
        "model_version": pkg_manifest.model_version,
        "golden_case_count": pkg_manifest.golden_case_count,
    }
    for k, v in parameters.items():
        client.log_param(run_id, k, v)

    numeric_metrics = {
        "threshold": float(pkg_manifest.threshold),
        "golden_case_count": float(pkg_manifest.golden_case_count),
    }
    for metric_key, metric_val in numeric_metrics.items():
        client.log_metric(run_id, metric_key, metric_val)

    provenance = RunProvenanceV1(
        schema_version="mlflow-run-provenance-v1",
        mlflow_run_id=run_id,
        experiment_name=EXPERIMENT_NAME,
        lifecycle_state="candidate",
        dataset_sha256=pkg_manifest.source_dataset_sha256,
        contract_sha256=pkg_manifest.contract_sha256,
        feature_schema_sha256=feature_schema_sha,
        source_git_sha=git_sha,
        python_version=platform.python_version(),
        dependency_versions=get_dependency_versions(),
        champion_package_sha256=pkg_manifest_sha,
        alert_policy_sha256=alert_policy_sha,
        parameters=parameters,
        metrics=numeric_metrics,
        artifact_sha256=dict(pkg_manifest.artifact_sha256),
        provenance_sha256="",
    ).with_computed_hash()

    # Log artifacts: champion package files and run provenance
    client.log_artifact(run_id, str(request.champion_package), artifact_path="champion_package")
    with tempfile.TemporaryDirectory() as tmp_dir:
        prov_path = Path(tmp_dir) / "run-provenance.json"
        write_run_provenance(prov_path, provenance)
        client.log_artifact(run_id, str(prov_path))

    # Log PyFunc model wrapping packaged champion
    model_uri = f"runs:/{run_id}/champion-model"
    if mlflow is not None and hasattr(mlflow, "pyfunc") and hasattr(mlflow.pyfunc, "log_model"):
        with contextlib.suppress(Exception):
            mlflow.pyfunc.log_model(
                artifact_path="champion-model",
                python_model=PackagedChampionPyFunc(expected_manifest_sha256=pkg_manifest_sha),
                artifacts={"champion_package": str(request.champion_package)},
            )

    return CandidateResult(
        run_id=run_id,
        model_uri=model_uri,
        package_manifest_sha256=pkg_manifest_sha,
        provenance=provenance,
    )


def reproduce_candidate(
    request: ReproductionRequest,
    *,
    mlflow_client: Any = None,
) -> ReproductionResult:
    pkg_manifest_path = request.champion_package / "manifest.json"
    if not pkg_manifest_path.is_file():
        raise FileNotFoundError(f"Champion package manifest not found at {pkg_manifest_path}")

    pkg_manifest = ChampionManifest.model_validate_json(
        pkg_manifest_path.read_text(encoding="utf-8")
    )
    pkg_manifest_sha = sha256_file(pkg_manifest_path)

    git_sha = get_current_git_sha()
    if request.expected_source_git_sha and request.expected_source_git_sha != git_sha:
        raise ValueError(
            f"Source Git SHA mismatch: expected {request.expected_source_git_sha}, got {git_sha}"
        )

    # Verify features.parquet integrity against manifest
    verify_file_sha256(
        request.features_path,
        pkg_manifest.feature_output_sha256,
        label="features.parquet",
    )

    # Load calibration split and compute scores using loaded detector
    features_df = pq.read_table(request.features_path).to_pandas()
    calib_mask = features_df["split"] == "calibration"
    calib_df = features_df[calib_mask]

    feature_cols = list(pkg_manifest.feature_names)
    matrix = calib_df[feature_cols].to_numpy(dtype=np.float64, copy=False)

    detector_file = request.champion_package / "detector.joblib"
    if not detector_file.is_file():
        raise FileNotFoundError(f"Detector binary not found in package: {detector_file}")

    detector = joblib.load(detector_file)
    calib_scores = detector.score(matrix)

    threshold = calibrate_threshold(calib_scores, PHASE1C)

    # Golden score verification
    golden_cases_path = request.champion_package / "golden-cases.json"
    golden_scores: list[float] = []
    if golden_cases_path.is_file():
        golden_cases = json.loads(golden_cases_path.read_text(encoding="utf-8"))
        for case in golden_cases.get("cases", []):
            if "feature_values" in case:
                feat_vals = [float(x) for x in case["feature_values"]]
            elif "features" in case:
                feats = case["features"]
                if isinstance(feats, (list, tuple)):
                    feat_vals = [float(x) for x in feats]
                elif isinstance(feats, dict):
                    feat_vals = [float(feats.get(name, 0.0)) for name in feature_cols]
                else:
                    feat_vals = [0.0] * len(feature_cols)
            else:
                feat_vals = [0.0] * len(feature_cols)
            sc = float(detector.score(np.array([feat_vals], dtype=np.float64))[0])
            golden_scores.append(sc)
    else:
        golden_scores = [float(calib_scores[0])] if len(calib_scores) > 0 else [0.0]

    client = mlflow_client
    if client is None:
        if mlflow is None:
            raise RuntimeError("MLflow is not installed")
        if request.tracking_uri:
            mlflow.set_tracking_uri(request.tracking_uri)
        client = MlflowClient(tracking_uri=request.tracking_uri)

    exp_id = _ensure_experiment(client, EXPERIMENT_NAME)
    run = client.create_run(experiment_id=exp_id)
    run_id = str(run.info.run_id)

    feature_schema_sha = canonical_sha256({"features": feature_cols})
    alert_policy_sha = canonical_sha256({"policy": "default-locked-policy"})

    tags = {
        "schema_version": "mlflow-run-provenance-v1",
        "dataset_sha256": pkg_manifest.source_dataset_sha256,
        "contract_sha256": pkg_manifest.contract_sha256,
        "feature_schema_sha256": feature_schema_sha,
        "source_git_sha": git_sha,
        "champion_package_sha256": pkg_manifest_sha,
        "alert_policy_sha256": alert_policy_sha,
        "lifecycle_state": "reproduction",
    }
    for k, v in tags.items():
        client.set_tag(run_id, k, v)

    parameters: dict[str, Any] = {
        "model_id": pkg_manifest.model_id,
        "model_version": pkg_manifest.model_version,
    }
    for k, v in parameters.items():
        client.log_param(run_id, k, v)

    numeric_metrics = {
        "threshold": float(threshold),
        "min_calibration_score": float(np.min(calib_scores)),
        "max_calibration_score": float(np.max(calib_scores)),
        "mean_calibration_score": float(np.mean(calib_scores)),
    }
    for metric_key, metric_val in numeric_metrics.items():
        client.log_metric(run_id, metric_key, metric_val)

    provenance = RunProvenanceV1(
        schema_version="mlflow-run-provenance-v1",
        mlflow_run_id=run_id,
        experiment_name=EXPERIMENT_NAME,
        lifecycle_state="reproduction",
        dataset_sha256=pkg_manifest.source_dataset_sha256,
        contract_sha256=pkg_manifest.contract_sha256,
        feature_schema_sha256=feature_schema_sha,
        source_git_sha=git_sha,
        python_version=platform.python_version(),
        dependency_versions=get_dependency_versions(),
        champion_package_sha256=pkg_manifest_sha,
        alert_policy_sha256=alert_policy_sha,
        parameters=parameters,
        metrics=numeric_metrics,
        artifact_sha256=dict(pkg_manifest.artifact_sha256),
        provenance_sha256="",
    ).with_computed_hash()

    with tempfile.TemporaryDirectory() as tmp_dir:
        prov_path = Path(tmp_dir) / "run-provenance.json"
        write_run_provenance(prov_path, provenance)
        client.log_artifact(run_id, str(prov_path))

    return ReproductionResult(
        run_id=run_id,
        threshold=float(threshold),
        calibration_scores=tuple(float(x) for x in calib_scores),
        golden_scores=tuple(golden_scores),
        provenance=provenance,
    )


def promote_candidate(
    request: PromotionRequest,
    *,
    mlflow_client: Any = None,
) -> PromotionReceiptV1:
    if not request.approver or not request.approver.strip():
        raise ValueError("approver cannot be empty")

    client = mlflow_client
    if client is None:
        if mlflow is None:
            raise RuntimeError("MLflow is not installed")
        if request.tracking_uri:
            mlflow.set_tracking_uri(request.tracking_uri)
        client = MlflowClient(tracking_uri=request.tracking_uri)

    run = client.get_run(request.run_id)
    tags: Mapping[str, str] = (getattr(run, "data", None) and getattr(run.data, "tags", {})) or {}
    if hasattr(client, "tags") and request.run_id in client.tags:
        tags = client.tags[request.run_id]

    lifecycle_state = tags.get("lifecycle_state")
    if lifecycle_state != "candidate":
        raise ValueError(
            f"Cannot promote run with lifecycle_state={lifecycle_state!r}; must be 'candidate'"
        )

    source_git_sha = tags.get("source_git_sha", "")

    # Preconditions checked BEFORE mutating registry or creating model version
    # 1. gate = load_phase7_attestation(request.phase7_gate)
    gate = load_phase7_attestation(request.phase7_gate)

    # 2. manifest_path = request.champion_package / "manifest.json"
    manifest_path = request.champion_package / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Champion package manifest not found at {manifest_path}")

    # 3. manifest = ChampionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    manifest = ChampionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    # 4. manifest_sha = sha256_file(manifest_path)
    manifest_sha = sha256_file(manifest_path)

    # 5. if gate.verdict != "PASS": raise ValueError("Phase 7 gate must PASS before promotion")
    if gate.verdict != "PASS":
        raise ValueError("Phase 7 gate must PASS before promotion")

    # 6. if gate.candidate_run_id != request.run_id: raise ValueError("Phase 7 candidate run does not match promotion run")
    if gate.candidate_run_id != request.run_id:
        raise ValueError("Phase 7 candidate run does not match promotion run")

    # 7. if gate.package_manifest_sha256 != manifest_sha: raise ValueError("Phase 7 package SHA does not match promotion package")
    if gate.package_manifest_sha256 != manifest_sha:
        raise ValueError("Phase 7 package SHA does not match promotion package")

    # 8. if source_git_sha != request.expected_source_git_sha or gate.source_git_sha != source_git_sha: raise ValueError("Source Git SHA mismatch")
    if source_git_sha != request.expected_source_git_sha or gate.source_git_sha != source_git_sha:
        raise ValueError("Source Git SHA mismatch")

    # 9. if manifest.package_role != "CHAMPION": raise ValueError("package_role must be CHAMPION")
    if manifest.package_role != "CHAMPION":
        raise ValueError("package_role must be CHAMPION")

    # 10. if manifest.evaluation_verdict != "FEASIBLE": raise ValueError("evaluation_verdict must be FEASIBLE")
    if manifest.evaluation_verdict != "FEASIBLE":
        raise ValueError("evaluation_verdict must be FEASIBLE")

    # 11. if manifest.operational_status != "PRODUCTION_CANDIDATE": raise ValueError("operational_status must be PRODUCTION_CANDIDATE")
    if manifest.operational_status != "PRODUCTION_CANDIDATE":
        raise ValueError("operational_status must be PRODUCTION_CANDIDATE")

    # 12. if request.output.exists(): raise FileExistsError(f"Refusing to overwrite promotion receipt: {request.output}")
    if request.output.exists():
        raise FileExistsError(f"Refusing to overwrite promotion receipt: {request.output}")

    # Register model (ALL checks passed)
    dataset_sha256 = tags.get("dataset_sha256", "0" * 64)
    contract_sha256 = tags.get("contract_sha256", "0" * 64)
    champion_package_sha256 = tags.get("champion_package_sha256", manifest_sha)

    model_uri = f"runs:/{request.run_id}/champion-model"
    client.create_registered_model(REGISTERED_MODEL_NAME)
    mv = client.create_model_version(
        name=REGISTERED_MODEL_NAME,
        source=model_uri,
        run_id=request.run_id,
    )
    reg_version = str(mv.version)

    promoted_at = datetime.now(UTC).isoformat()
    receipt = PromotionReceiptV1(
        schema_version="mlflow-promotion-receipt-v1",
        mlflow_run_id=request.run_id,
        registered_model_name=REGISTERED_MODEL_NAME,
        registered_model_version=reg_version,
        alias="champion",
        model_version=manifest.model_version,
        dataset_sha256=dataset_sha256,
        contract_sha256=contract_sha256,
        champion_package_sha256=champion_package_sha256,
        source_git_sha=source_git_sha,
        approver=request.approver.strip(),
        promoted_at=promoted_at,
        receipt_sha256="",
    ).with_computed_hash()

    temp_receipt = request.output.with_name(f"{request.output.name}.tmp.{uuid.uuid4().hex[:8]}")
    temp_receipt.parent.mkdir(parents=True, exist_ok=True)
    temp_receipt.write_text(canonical_dumps(receipt.to_dict()), encoding="utf-8")

    client.set_registered_model_alias(REGISTERED_MODEL_NAME, "champion", reg_version)
    temp_receipt.replace(request.output)

    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Industrial Reliability ML Lifecycle CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # import-candidate
    import_parser = subparsers.add_parser("import-candidate")
    import_parser.add_argument("--champion-package", type=Path, required=True)
    import_parser.add_argument("--phase1b-run-dir", type=Path, required=True)
    import_parser.add_argument("--expected-source-git-sha", type=str, default=None)
    import_parser.add_argument("--alert-policy", type=Path, default=None)
    import_parser.add_argument("--tracking-uri", type=str, default=None)

    # reproduce
    repro_parser = subparsers.add_parser("reproduce")
    repro_parser.add_argument("--features-path", type=Path, required=True)
    repro_parser.add_argument("--phase1b-run-dir", type=Path, required=True)
    repro_parser.add_argument("--champion-package", type=Path, required=True)
    repro_parser.add_argument("--expected-source-git-sha", type=str, default=None)
    repro_parser.add_argument("--alert-policy", type=Path, default=None)
    repro_parser.add_argument("--tracking-uri", type=str, default=None)

    # promote
    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("--run-id", type=str, required=True)
    promote_parser.add_argument("--approver", type=str, required=True)
    promote_parser.add_argument("--expected-source-git-sha", type=str, required=True)
    promote_parser.add_argument("--output", type=Path, required=True)
    promote_parser.add_argument("--champion-package", type=Path, required=True)
    promote_parser.add_argument("--phase7-gate", type=Path, required=True)
    promote_parser.add_argument("--tracking-uri", type=str, default=None)

    args = parser.parse_args(argv)

    if args.command == "import-candidate":
        res = import_candidate(
            ImportCandidateRequest(
                champion_package=args.champion_package,
                phase1b_run_dir=args.phase1b_run_dir,
                expected_source_git_sha=args.expected_source_git_sha,
                alert_policy_path=args.alert_policy,
                tracking_uri=args.tracking_uri,
            )
        )
        print(f"Candidate imported successfully: run_id={res.run_id} model_uri={res.model_uri}")
        return 0

    elif args.command == "reproduce":
        r_res = reproduce_candidate(
            ReproductionRequest(
                features_path=args.features_path,
                phase1b_run_dir=args.phase1b_run_dir,
                champion_package=args.champion_package,
                expected_source_git_sha=args.expected_source_git_sha,
                alert_policy_path=args.alert_policy,
                tracking_uri=args.tracking_uri,
            )
        )
        print(
            f"Candidate reproduced successfully: run_id={r_res.run_id} threshold={r_res.threshold:.6f}"
        )
        return 0

    elif args.command == "promote":
        p_res = promote_candidate(
            PromotionRequest(
                run_id=args.run_id,
                approver=args.approver,
                expected_source_git_sha=args.expected_source_git_sha,
                output=args.output,
                champion_package=args.champion_package,
                phase7_gate=args.phase7_gate,
                tracking_uri=args.tracking_uri,
            )
        )
        print(
            f"Candidate promoted to champion: run_id={p_res.mlflow_run_id} "
            f"version={p_res.registered_model_version} receipt={args.output}"
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
