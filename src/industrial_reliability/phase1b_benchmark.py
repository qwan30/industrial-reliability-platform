"""Reproducible Phase 1B benchmark runner, evaluation ladder, and artifact publisher."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from numpy.typing import NDArray

from industrial_reliability.artifact_integrity import (
    ArtifactIntegrityError,
    load_self_hashed_manifest,
    verify_file_sha256,
    verify_prepared_parquet,
)
from industrial_reliability.autoencoder import DenseAutoencoderDetector
from industrial_reliability.evaluation import (
    EvaluationResult,
    build_episodes,
    calibrate_threshold,
    evaluate,
)
from industrial_reliability.ml_provenance import validate_git_sha
from industrial_reliability.models import (
    IsolationForestDetector,
    RobustStatisticalDetector,
)
from industrial_reliability.phase1b_contracts import (
    PHASE1C,
    Phase1BContract,
    metropt3_contract_manifest,
    phase1b_evaluation_events,
)
from industrial_reliability.phase1b_data import sha256_file

type ModelId = Literal["statistical", "isolation_forest", "autoencoder"]
MODEL_IDS: tuple[ModelId, ...] = ("statistical", "isolation_forest", "autoencoder")


@dataclass(frozen=True, slots=True)
class LockedThreshold:
    split: Literal["calibration"] = "calibration"
    quantile: float = 0.995
    method: Literal["higher"] = "higher"


@dataclass(frozen=True, slots=True)
class FittedCandidate:
    model_id: ModelId
    detector: RobustStatisticalDetector | IsolationForestDetector | DenseAutoencoderDetector
    threshold: float
    threshold_provenance: LockedThreshold


@dataclass(frozen=True, slots=True)
class CandidateResult:
    model_id: ModelId
    fitted: FittedCandidate
    scores_df: pd.DataFrame
    evaluation: EvaluationResult


@dataclass(frozen=True, slots=True)
class Phase1BBenchmarkResult:
    run_dir: Path
    verdict: Literal["FEASIBLE", "NOT FEASIBLE"]
    selected_model: ModelId | None
    contract_sha256: str
    source_dataset_sha256: str
    run_id: str


def detector_for(
    model_id: ModelId,
    contract: Phase1BContract = PHASE1C,
) -> RobustStatisticalDetector | IsolationForestDetector | DenseAutoencoderDetector:
    if model_id == "statistical":
        return RobustStatisticalDetector()
    if model_id == "isolation_forest":
        return IsolationForestDetector()
    if model_id == "autoencoder":
        return DenseAutoencoderDetector(epochs=contract.autoencoder_epochs)
    raise ValueError(f"Unknown model_id: {model_id}")


def fit_phase1b_candidate(
    *,
    model_id: ModelId,
    train_features: NDArray[np.float64],
    calibration_features: NDArray[np.float64],
    contract: Phase1BContract = PHASE1C,
) -> FittedCandidate:
    detector = detector_for(model_id, contract).fit(train_features)
    calib_scores = detector.score(calibration_features)
    threshold = calibrate_threshold(calib_scores, contract)
    return FittedCandidate(
        model_id=model_id,
        detector=detector,
        threshold=threshold,
        threshold_provenance=LockedThreshold(
            split="calibration",
            quantile=contract.threshold_quantile,
            method=cast(Literal["higher"], contract.threshold_method),
        ),
    )


def evaluate_candidate_holdout(
    fitted: FittedCandidate,
    holdout_df: pd.DataFrame,
    active_features: tuple[str, ...],
    contract: Phase1BContract = PHASE1C,
) -> CandidateResult:
    feature_matrix = holdout_df[list(active_features)].to_numpy(dtype=np.float64)
    scores = fitted.detector.score(feature_matrix)

    scores_df = pd.DataFrame(
        {
            "model_id": fitted.model_id,
            "split": "holdout",
            "window_start": holdout_df["window_start"].to_numpy(),
            "window_end": holdout_df["window_end"].to_numpy(),
            "score": scores,
            "threshold": fitted.threshold,
            "is_anomaly": scores >= fitted.threshold,
        }
    )

    events = phase1b_evaluation_events()
    episodes = build_episodes(scores_df, fitted.threshold, contract)
    eval_result = evaluate(
        scores_df,
        episodes,
        fitted.threshold,
        events,
        contract,
    )

    return CandidateResult(
        model_id=fitted.model_id,
        fitted=fitted,
        scores_df=scores_df,
        evaluation=eval_result,
    )


def _serialize_candidate_evaluation(res: EvaluationResult) -> dict[str, Any]:
    return {
        "threshold": res.threshold,
        "valid_holdout_decisions": res.valid_holdout_decisions,
        "anomalous_decisions": res.anomalous_decisions,
        "time_in_alert": res.time_in_alert,
        "pr_auc": res.pr_auc,
        "detected_events": res.detected_events,
        "total_events": res.total_events,
        "false_episodes": res.false_episodes,
        "false_episodes_per_day": res.false_episodes_per_day,
        "feasible": res.feasible,
        "event_results": [
            {
                "event_id": er.event_id,
                "detected": er.detected,
                "first_detection_time": (
                    er.first_detection_time.isoformat() if er.first_detection_time else None
                ),
                "lead_seconds_to_source_start": er.lead_seconds_to_source_start,
            }
            for er in res.event_results
        ],
    }


def run_phase1b_benchmark(
    prepared_dir: Path,
    feature_path: Path,
    artifact_dir: Path,
    expected_prepared_output_sha256: str,
    source_git_sha: str,
    contract: Phase1BContract = PHASE1C,
) -> Phase1BBenchmarkResult:
    resolved_prep = prepared_dir.resolve()
    resolved_feat = feature_path.resolve()
    prep_parquet_file = (resolved_prep / "telemetry.parquet").resolve()
    prep_manifest_file = (resolved_prep / "manifest.json").resolve()
    feat_manifest_file = (resolved_feat.parent / "feature_manifest.json").resolve()
    if (
        not prep_parquet_file.is_file()
        or not prep_manifest_file.is_file()
        or not feat_manifest_file.is_file()
        or not resolved_feat.is_file()
    ):
        raise FileNotFoundError("Prerequisite manifest files missing")

    contract_manifest = metropt3_contract_manifest(contract)
    expected_contract_sha = str(contract_manifest["contract_sha256"])

    verified_data = verify_prepared_parquet(
        prep_parquet_file,
        expected_contract_sha256=expected_contract_sha,
        expected_source_dataset_sha256=contract.archive_sha256,
        expected_output_sha256=expected_prepared_output_sha256,
    )
    feat_manifest = load_self_hashed_manifest(feat_manifest_file)
    verify_file_sha256(
        resolved_feat, str(feat_manifest.get("output_sha256", "")), "features.parquet"
    )

    if feat_manifest.get("contract_sha256") != expected_contract_sha:
        raise ArtifactIntegrityError(
            f"features contract SHA-256 mismatch: expected {expected_contract_sha}, got {feat_manifest.get('contract_sha256')}"
        )
    if feat_manifest.get("data_manifest_sha256") != verified_data.manifest_sha256:
        raise ArtifactIntegrityError(
            f"features data manifest mismatch: expected {verified_data.manifest_sha256}, got {feat_manifest.get('data_manifest_sha256')}"
        )

    active_features = tuple(feat_manifest["active_feature_names"])
    features_df = pq.read_table(resolved_feat).to_pandas()

    train_df = features_df[features_df["split"] == "train"]
    calib_df = features_df[features_df["split"] == "calibration"]
    holdout_df = features_df[features_df["split"] == "holdout"]

    train_matrix = train_df[list(active_features)].to_numpy(dtype=np.float64)
    calib_matrix = calib_df[list(active_features)].to_numpy(dtype=np.float64)

    run_id = f"phase1b-run-{uuid.uuid4().hex[:12]}"
    run_dir = (artifact_dir.resolve() / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    models_dir = (run_dir / "models").resolve()
    models_dir.mkdir(parents=True, exist_ok=True)

    # Save evidence baseline (train median & MAD)
    train_median = np.median(train_matrix, axis=0)
    train_mad = np.median(np.abs(train_matrix - train_median), axis=0)
    evidence_baseline_path = (run_dir / "evidence-baseline.npz").resolve()
    np.savez_compressed(
        evidence_baseline_path,
        feature_names=np.array(active_features),
        median=train_median,
        mad=train_mad,
    )

    all_scores = []
    candidate_results: list[CandidateResult] = []

    for model_id in MODEL_IDS:
        fitted = fit_phase1b_candidate(
            model_id=model_id,
            train_features=train_matrix,
            calibration_features=calib_matrix,
            contract=contract,
        )
        # Save model joblib
        model_path = (models_dir / f"{model_id}.joblib").resolve()
        joblib.dump(fitted.detector, model_path)

        res = evaluate_candidate_holdout(fitted, holdout_df, active_features, contract)
        candidate_results.append(res)
        all_scores.append(res.scores_df)

    # Save combined scores
    combined_scores = pd.concat(all_scores, ignore_index=True)
    scores_path = (run_dir / "scores.parquet").resolve()
    table = pa.Table.from_pandas(combined_scores, preserve_index=False)
    pq.write_table(table, scores_path, compression="snappy")

    # Model selection ladder (simplest passing model)
    passing_candidates = [cr for cr in candidate_results if cr.evaluation.feasible]
    selected = passing_candidates[0] if passing_candidates else None
    verdict: Literal["FEASIBLE", "NOT FEASIBLE"] = (
        "FEASIBLE" if selected is not None else "NOT FEASIBLE"
    )
    selected_model = selected.model_id if selected else None

    # Write private run manifest
    run_manifest = {
        "schema_version": "phase1b-run-v1",
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "verdict": verdict,
        "selected_model": selected_model,
        "contract_sha256": feat_manifest["contract_sha256"],
        "source_dataset_sha256": verified_data.source_dataset_sha256,
        "prepared_output_sha256": verified_data.parquet_sha256,
        "feature_output_sha256": str(feat_manifest["output_sha256"]),
        "source_git_sha": validate_git_sha(source_git_sha),
        "models": {
            cr.model_id: _serialize_candidate_evaluation(cr.evaluation) for cr in candidate_results
        },
    }

    manifest_path = (run_dir / "run_manifest.json").resolve()
    manifest_path.write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")

    # If FEASIBLE, write champion-manifest.json
    if selected is not None:
        champion_manifest = {
            "schema_version": "phase1b-champion-v1",
            "run_id": run_id,
            "verdict": "FEASIBLE",
            "model_id": selected.model_id,
            "model_version": f"champion-{selected.model_id}-v1",
            "threshold": selected.fitted.threshold,
            "threshold_provenance": asdict(selected.fitted.threshold_provenance),
            "active_feature_names": list(active_features),
            "contract_sha256": feat_manifest["contract_sha256"],
            "source_dataset_sha256": verified_data.source_dataset_sha256,
            "prepared_output_sha256": verified_data.parquet_sha256,
            "feature_output_sha256": feat_manifest["output_sha256"],
            "artifact_sha256": {
                "scores_parquet": sha256_file(scores_path),
                "model_binary": sha256_file(models_dir / f"{selected.model_id}.joblib"),
                "evidence_baseline": sha256_file(evidence_baseline_path),
            },
        }
        (run_dir / "champion-manifest.json").resolve().write_text(
            json.dumps(champion_manifest, indent=2), encoding="utf-8"
        )

    return Phase1BBenchmarkResult(
        run_dir=run_dir,
        verdict=verdict,
        selected_model=selected_model,
        contract_sha256=feat_manifest["contract_sha256"],
        source_dataset_sha256=verified_data.source_dataset_sha256,
        run_id=run_id,
    )


def publish_phase1b_results(
    run_dir: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    resolved_run_dir = run_dir.resolve()
    manifest_file = (resolved_run_dir / "run_manifest.json").resolve()
    if not manifest_file.is_file():
        raise FileNotFoundError(f"run_manifest.json missing in {resolved_run_dir}")

    run_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    resolved_output = output_dir.resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)

    metrics_file = (resolved_output / "phase-1b-metrics.json").resolve()
    report_file = (resolved_output / "phase-1b-metropt3-fresh-validation.md").resolve()

    published_metrics = {
        "schema_version": "phase1b-benchmark-v1",
        "run_id": run_manifest["run_id"],
        "timestamp": run_manifest["timestamp"],
        "verdict": run_manifest["verdict"],
        "selected_model": run_manifest["selected_model"],
        "contract_sha256": run_manifest["contract_sha256"],
        "source_dataset_sha256": run_manifest["source_dataset_sha256"],
        "prepared_output_sha256": run_manifest["prepared_output_sha256"],
        "feature_output_sha256": run_manifest["feature_output_sha256"],
        "source_git_sha": run_manifest["source_git_sha"],
        "models": run_manifest["models"],
    }
    metrics_file.write_text(json.dumps(published_metrics, indent=2), encoding="utf-8")

    # Generate Markdown Report
    lines = [
        "# Phase 1B MetroPT-3 Fresh Validation Results",
        "",
        f"- **Verdict:** `{run_manifest['verdict']}`",
        f"- **Selected Model:** `{run_manifest['selected_model']}`",
        f"- **Contract SHA-256:** `{run_manifest['contract_sha256']}`",
        f"- **Source Dataset SHA-256:** `{run_manifest['source_dataset_sha256']}`",
        "",
        "## Model Evaluation Comparison",
        "",
        "| Model | Detected Events | False Episodes/Day | Time in Alert | PR-AUC | Feasible |",
        "|---|---|---|---|---|---|",
    ]
    for model_id, m in run_manifest["models"].items():
        lines.append(
            f"| `{model_id}` | {m['detected_events']}/{m['total_events']} | {m['false_episodes_per_day']:.3f} | {m['time_in_alert'] * 100:.2f}% | {m['pr_auc']:.4f} | `{m['feasible']}` |"
        )

    lines.extend(
        [
            "",
            "## Individual Event Detections",
            "",
            "| Model | Event ID | Detected | Lead Time (seconds) |",
            "|---|---|---|---|",
        ]
    )
    for model_id, m in run_manifest["models"].items():
        for er in m["event_results"]:
            lead = (
                f"{er['lead_seconds_to_source_start']:.0f}"
                if er["lead_seconds_to_source_start"] is not None
                else "N/A"
            )
            lines.append(f"| `{model_id}` | `{er['event_id']}` | `{er['detected']}` | {lead} |")

    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return metrics_file, report_file


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run Phase 1B benchmark.")
    parser.add_argument(
        "--prepared-dir", type=Path, required=True, help="Directory with prepared telemetry"
    )
    parser.add_argument(
        "--prepared-output-sha256",
        type=str,
        required=True,
        help="Expected SHA-256 digest of prepared telemetry.parquet",
    )
    parser.add_argument("--features", type=Path, required=True, help="Path to features.parquet")
    parser.add_argument(
        "--artifact-dir", type=Path, required=True, help="Directory for private artifacts"
    )
    parser.add_argument(
        "--publish-dir", type=Path, required=True, help="Directory for published metrics/report"
    )
    parser.add_argument(
        "--source-git-sha",
        type=str,
        required=True,
        help="Git commit SHA-256 (40-character hex) corresponding to this run",
    )
    args = parser.parse_args()

    result = run_phase1b_benchmark(
        prepared_dir=args.prepared_dir,
        feature_path=args.features,
        artifact_dir=args.artifact_dir,
        expected_prepared_output_sha256=args.prepared_output_sha256,
        source_git_sha=args.source_git_sha,
    )
    publish_phase1b_results(result.run_dir, args.publish_dir)
    print(
        f"Phase 1B benchmark complete: Verdict = {result.verdict}, Selected Model = {result.selected_model}"
    )


if __name__ == "__main__":
    main()
