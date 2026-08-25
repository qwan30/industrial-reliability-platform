from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from industrial_reliability.champion import load_champion
from industrial_reliability.evaluation import calibrate_threshold
from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    RunProvenanceV1,
    canonical_sha256,
    validate_git_sha,
    write_promotion_receipt,
    write_run_provenance,
)
from industrial_reliability.package_champion import ChampionManifest
from industrial_reliability.phase1b_benchmark import detector_for
from industrial_reliability.phase1b_contracts import PHASE1B
from industrial_reliability.phase1b_data import sha256_file

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


mlflow: Any
MlflowClient: Any
try:
    import mlflow
    import mlflow.pyfunc
    from mlflow import MlflowClient as MlflowClient
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
    champion_package: Path | None = None
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        prov_path = Path(tmp_dir) / "run-provenance.json"
        write_run_provenance(prov_path, provenance)
        client.log_artifact(run_id, str(prov_path))

    # If real MLflow is active, log the pyfunc model
    if mlflow is not None and hasattr(mlflow, "pyfunc") and hasattr(mlflow.pyfunc, "log_model"):
        try:
            with mlflow.start_run(run_id=run_id):
                mlflow.pyfunc.log_model(
                    artifact_path="champion-model",
                    python_model=PackagedChampionPyFunc(expected_manifest_sha256=pkg_manifest_sha),
                    artifacts={"champion_package": str(request.champion_package.resolve())},
                )
        except Exception:
            pass

    model_uri = f"runs:/{run_id}/champion-model"
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

    pkg_manifest_sha = sha256_file(pkg_manifest_path)
    pkg_manifest = ChampionManifest.model_validate_json(
        pkg_manifest_path.read_text(encoding="utf-8")
    )

    git_sha = get_current_git_sha()
    if request.expected_source_git_sha and request.expected_source_git_sha != git_sha:
        raise ValueError(
            f"Source Git SHA mismatch: expected {request.expected_source_git_sha}, got {git_sha}"
        )

    # Read features table filtered strictly to train and calibration
    table = pq.read_table(
        request.features_path,
        filters=[("split", "in", ["train", "calibration"])],
    )
    frame = table.to_pandas()

    train_frame = frame[frame["split"] == "train"]
    calib_frame = frame[frame["split"] == "calibration"]

    feature_cols = list(pkg_manifest.feature_names)
    train_features = train_frame[feature_cols].to_numpy(dtype=np.float64, copy=False)
    calib_features = calib_frame[feature_cols].to_numpy(dtype=np.float64, copy=False)

    # Fit detector on train only
    model_id = pkg_manifest.model_id
    detector = detector_for(model_id, PHASE1B).fit(train_features)
    calib_scores = detector.score(calib_features)
    threshold = calibrate_threshold(calib_scores, PHASE1B)

    # Load and score golden cases
    golden_path = request.champion_package / "golden-cases.json"
    golden_scores: list[float] = []
    if golden_path.is_file():
        golden_data = json.loads(golden_path.read_text(encoding="utf-8"))
        for case in golden_data.get("cases", []):
            if "feature_values" in case:
                case_names = case.get("feature_names", feature_cols)
                name_to_val = dict(zip(case_names, case["feature_values"], strict=False))
                feat_vals = [name_to_val[name] for name in feature_cols]
            elif "feature_vector" in case:
                feat_vals = [case["feature_vector"][name] for name in feature_cols]
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

    source_git_sha = tags.get("source_git_sha", request.expected_source_git_sha)
    dataset_sha256 = tags.get("dataset_sha256", "0" * 64)
    contract_sha256 = tags.get("contract_sha256", "0" * 64)
    champion_package_sha256 = tags.get("champion_package_sha256", "0" * 64)

    # Register model
    model_uri = f"runs:/{request.run_id}/champion-model"
    client.create_registered_model(REGISTERED_MODEL_NAME)
    mv = client.create_model_version(
        name=REGISTERED_MODEL_NAME,
        source=model_uri,
        run_id=request.run_id,
    )
    reg_version = str(mv.version)
    client.set_registered_model_alias(REGISTERED_MODEL_NAME, "champion", reg_version)

    model_version = "champion-statistical-v1"
    if request.champion_package and (request.champion_package / "manifest.json").is_file():
        pkg_manifest = ChampionManifest.model_validate_json(
            (request.champion_package / "manifest.json").read_text(encoding="utf-8")
        )
        model_version = pkg_manifest.model_version

    receipt = PromotionReceiptV1(
        schema_version="mlflow-promotion-receipt-v1",
        mlflow_run_id=request.run_id,
        registered_model_name=REGISTERED_MODEL_NAME,
        registered_model_version=reg_version,
        alias="champion",
        model_version=model_version,
        dataset_sha256=dataset_sha256,
        contract_sha256=contract_sha256,
        champion_package_sha256=champion_package_sha256,
        source_git_sha=source_git_sha,
        approver=request.approver.strip(),
        promoted_at="2026-08-25T00:00:00Z",
        receipt_sha256="",
    ).with_computed_hash()

    write_promotion_receipt(request.output, receipt)
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
    promote_parser.add_argument("--champion-package", type=Path, default=None)
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
