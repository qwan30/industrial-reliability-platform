"""One reproducible, offline Phase 1 benchmark command."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from typing import cast

import numpy as np
import pandas as pd

from industrial_reliability.autoencoder import DenseAutoencoderDetector
from industrial_reliability.contracts import PHASE1, Phase1Contract, contract_manifest
from industrial_reliability.data import prepare_dataset, sha256_file
from industrial_reliability.evaluation import (
    build_episodes,
    calibrate_threshold,
    evaluate,
)
from industrial_reliability.features import build_features
from industrial_reliability.models import IsolationForestDetector, RobustStatisticalDetector

SCHEMA_VERSION = "phase1-benchmark-v1"
MIN_FREE_BYTES = 10 * 1024**3
MODEL_IDS = ("statistical", "isolation_forest", "autoencoder")
ARTIFACT_NAMES = (
    "data_manifest.json",
    "feature_manifest.json",
    "scores.parquet",
    "episodes.json",
    "event_results.json",
    "metrics.json",
    "limitations.md",
)
DEPENDENCIES = ("numpy", "pandas", "pyarrow", "scikit-learn", "torch")


@dataclass(frozen=True)
class BenchmarkResult:
    run_dir: Path
    manifest: Mapping[str, object]
    metrics: Mapping[str, Mapping[str, object]]


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(_canonical_json(value) + "\n", encoding="utf-8")


def _existing_parent(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists():
        if candidate.parent == candidate:
            return candidate
        candidate = candidate.parent
    return candidate


def _check_disk(work_dir: Path) -> None:
    if shutil.disk_usage(_existing_parent(work_dir)).free < MIN_FREE_BYTES:
        raise RuntimeError("Phase 1 benchmark requires at least 10 GiB free disk")


def _check_work_dir(work_dir: Path) -> None:
    if not work_dir.exists():
        return
    if not work_dir.is_dir() or next(work_dir.iterdir(), None) is not None:
        raise FileExistsError(f"work directory must be absent or empty, not nonempty: {work_dir}")


def _git_output(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _git_provenance(require_clean: bool) -> tuple[str, bool]:
    git_sha = _git_output("rev-parse", "HEAD").strip()
    entries = tuple(
        entry
        for entry in _git_output(
            "status",
            "--porcelain",
            "--untracked-files=all",
            "-z",
        ).split("\0")
        if entry
    )
    disallowed = []
    for entry in entries:
        status = entry[:2]
        path = entry[3:] if len(entry) >= 4 else entry
        if status == "??" and (path == ".codex" or path.startswith(".codex/")):
            continue
        disallowed.append(entry)
    clean = not disallowed
    if require_clean and not clean:
        raise RuntimeError(f"Git worktree has disallowed changes: {', '.join(disallowed)}")
    return git_sha, clean


def _model_parameters(contract: Phase1Contract, epochs: int) -> dict[str, dict[str, object]]:
    return {
        "statistical": {
            "robust_mad_scale": contract.robust_mad_scale,
            "aggregation": contract.statistical_aggregation,
        },
        "isolation_forest": {
            "n_estimators": contract.isolation_forest_estimators,
            "max_samples": contract.isolation_forest_max_samples,
            "contamination": contract.isolation_forest_contamination,
            "random_state": contract.random_seed,
            "n_jobs": contract.isolation_forest_n_jobs,
            "score_rule": contract.isolation_forest_score_rule,
        },
        "autoencoder": {
            "hidden_width": contract.autoencoder_hidden_width,
            "bottleneck_width": contract.autoencoder_bottleneck_width,
            "activation": contract.autoencoder_activation,
            "loss": contract.autoencoder_loss,
            "optimizer": contract.autoencoder_optimizer,
            "learning_rate": contract.autoencoder_learning_rate,
            "batch_size": contract.autoencoder_batch_size,
            "epochs": epochs,
            "device": contract.autoencoder_device,
            "deterministic": contract.autoencoder_deterministic,
            "num_workers": contract.autoencoder_num_workers,
            "scaler": contract.autoencoder_scaler,
        },
    }


def _limitations(contract: Phase1Contract) -> tuple[str, ...]:
    return (
        contract.dataset_license_status,
        contract.dataset_release_status,
        "Only three minute-precision failure intervals are available for holdout evaluation.",
        "Anomaly scores are correlation evidence and do not establish physical root cause.",
        "This is offline feasibility evidence, not a production alerting system.",
    )


def _split_bounds(contract: Phase1Contract) -> dict[str, dict[str, str]]:
    return {
        split.name: {
            "start": split.start.isoformat(timespec="seconds"),
            "end": split.end.isoformat(timespec="seconds"),
        }
        for split in (contract.train, contract.calibration, contract.holdout)
    }


def _dependencies() -> dict[str, str]:
    return {dependency: version(dependency) for dependency in DEPENDENCIES}


def run_benchmark(
    dataset: Path,
    work_dir: Path,
    artifact_dir: Path,
    contract: Phase1Contract = PHASE1,
    autoencoder_epochs: int | None = None,
    require_clean_git: bool = True,
) -> BenchmarkResult:
    """Prepare, fit, calibrate, evaluate, and write one local benchmark run."""
    dataset = Path(dataset)
    work_dir = Path(work_dir)
    artifact_dir = Path(artifact_dir)
    _check_work_dir(work_dir)
    _check_disk(work_dir)

    if type(contract.autoencoder_epochs) is not int or contract.autoencoder_epochs < 1:
        raise ValueError("contract autoencoder_epochs must be a positive built-in int")
    epochs = contract.autoencoder_epochs if autoencoder_epochs is None else autoencoder_epochs
    if type(epochs) is not int or epochs < 1:
        raise ValueError("effective autoencoder epochs must be a positive built-in int")
    if _canonical_json(_model_parameters(contract, contract.autoencoder_epochs)) != _canonical_json(
        _model_parameters(PHASE1, PHASE1.autoencoder_epochs)
    ):
        raise ValueError("contract model settings must match PHASE1 hardcoded detector settings")
    full_identity = (contract.dataset_sha256, contract.dataset_bytes, contract.dataset_rows) == (
        PHASE1.dataset_sha256,
        PHASE1.dataset_bytes,
        PHASE1.dataset_rows,
    )
    if full_identity and epochs != PHASE1.autoencoder_epochs:
        raise ValueError("full-run autoencoder epoch override must match PHASE1")
    git_sha, tracked_tree_clean = _git_provenance(require_clean_git)
    contract_sha256 = cast(str, contract_manifest(contract)["contract_sha256"])
    run_id = f"run-{contract_sha256[:12]}-{git_sha[:12]}"
    run_dir = artifact_dir / run_id
    if run_dir.exists():
        raise FileExistsError(f"benchmark run destination already exists: {run_dir}")

    prepared_dir = work_dir / "prepared"
    features_path = work_dir / "features.parquet"
    data_manifest = prepare_dataset(dataset, prepared_dir, contract)
    feature_manifest = build_features(prepared_dir, features_path, contract)
    feature_frame = pd.read_parquet(features_path)
    split_frames = {
        split.name: feature_frame.loc[feature_frame["split"] == split.name].reset_index(drop=True)
        for split in (contract.train, contract.calibration, contract.holdout)
    }
    missing_splits = [name for name, frame in split_frames.items() if frame.empty]
    if missing_splits:
        raise ValueError(f"missing feature windows for split(s): {', '.join(missing_splits)}")

    matrices = {
        name: frame.loc[:, contract.feature_columns].to_numpy(dtype=np.float64)
        for name, frame in split_frames.items()
    }
    parameters = _model_parameters(contract, epochs)
    metrics: dict[str, dict[str, object]] = {}
    episode_payload: dict[str, list[dict[str, object]]] = {}
    event_payload: dict[str, list[dict[str, object]]] = {}
    threshold_provenance: dict[str, dict[str, object]] = {}
    score_frames: list[pd.DataFrame] = []

    for model_id, detector in (
        ("statistical", RobustStatisticalDetector()),
        ("isolation_forest", IsolationForestDetector()),
        ("autoencoder", DenseAutoencoderDetector(epochs=epochs)),
    ):
        fit_started = perf_counter()
        fitted = detector.fit(matrices["train"])
        fit_seconds = perf_counter() - fit_started

        score_started = perf_counter()
        calibration_scores = fitted.score(matrices["calibration"])
        holdout_scores = fitted.score(matrices["holdout"])
        score_seconds = perf_counter() - score_started
        threshold = calibrate_threshold(calibration_scores, contract)

        holdout_frame = split_frames["holdout"].loc[:, ["window_start", "window_end"]].copy()
        holdout_frame["score"] = holdout_scores
        episodes = build_episodes(holdout_frame, threshold, contract)
        evaluation = evaluate(holdout_frame, episodes, threshold, contract.events, contract)
        serialized_evaluation = cast(dict[str, object], _jsonable(asdict(evaluation)))
        metrics[model_id] = {
            **serialized_evaluation,
            "fit_seconds": fit_seconds,
            "score_seconds": score_seconds,
            "model_parameters": parameters[model_id],
        }
        episode_payload[model_id] = [
            cast(dict[str, object], _jsonable(asdict(episode))) for episode in episodes
        ]
        event_payload[model_id] = [
            cast(dict[str, object], _jsonable(asdict(result)))
            for result in evaluation.event_results
        ]
        threshold_provenance[model_id] = {
            "split": contract.calibration.name,
            "quantile": contract.threshold_quantile,
            "method": contract.threshold_method,
            "threshold": threshold,
        }
        score_frames.append(
            pd.DataFrame(
                {
                    "window_start": holdout_frame["window_start"],
                    "window_end": holdout_frame["window_end"],
                    "split": contract.holdout.name,
                    "model_id": model_id,
                    "raw_score": holdout_scores,
                    "threshold": threshold,
                    "is_anomaly": (
                        holdout_scores >= threshold
                        if contract.anomaly_inclusive
                        else holdout_scores > threshold
                    ),
                }
            )
        )

    limitations = _limitations(contract)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    temporary_run = Path(tempfile.mkdtemp(prefix=f".{run_id}.tmp-", dir=artifact_dir))
    try:
        shutil.copyfile(prepared_dir / "manifest.json", temporary_run / "data_manifest.json")
        shutil.copyfile(
            features_path.with_suffix(".manifest.json"),
            temporary_run / "feature_manifest.json",
        )
        pd.concat(score_frames, ignore_index=True).to_parquet(
            temporary_run / "scores.parquet",
            index=False,
        )
        _write_json(temporary_run / "episodes.json", episode_payload)
        _write_json(temporary_run / "event_results.json", event_payload)
        _write_json(temporary_run / "metrics.json", metrics)
        (temporary_run / "limitations.md").write_text(
            "# Phase 1 Limitations\n\n"
            + "\n".join(f"- {limitation}" for limitation in limitations)
            + "\n",
            encoding="utf-8",
        )
        artifact_sha256 = {name: sha256_file(temporary_run / name) for name in ARTIFACT_NAMES}
        manifest: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "dataset_sha256": data_manifest.dataset_sha256,
            "contract_sha256": contract_sha256,
            "git_sha": git_sha,
            "tracked_tree_clean": tracked_tree_clean,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "dependencies": _dependencies(),
            "split_bounds": _split_bounds(contract),
            "window_seconds": contract.window_seconds,
            "stride_seconds": contract.stride_seconds,
            "feature_columns": list(feature_manifest.feature_columns),
            "model_parameters": parameters,
            "threshold_provenance": threshold_provenance,
            "holdout_evaluations": dict.fromkeys(MODEL_IDS, 1),
            "artifact_sha256": artifact_sha256,
            "limitations": list(limitations),
        }
        _write_json(temporary_run / "manifest.json", manifest)
        temporary_run.rename(run_dir)
    except BaseException:
        shutil.rmtree(temporary_run, ignore_errors=True)
        raise

    return BenchmarkResult(
        run_dir=run_dir,
        manifest=MappingProxyType(manifest),
        metrics=MappingProxyType(
            {model_id: MappingProxyType(payload) for model_id, payload in metrics.items()}
        ),
    )


_MANIFEST_FIELDS = {
    "schema_version",
    "run_id",
    "dataset_sha256",
    "contract_sha256",
    "git_sha",
    "tracked_tree_clean",
    "python_version",
    "platform",
    "dependencies",
    "split_bounds",
    "window_seconds",
    "stride_seconds",
    "feature_columns",
    "model_parameters",
    "threshold_provenance",
    "holdout_evaluations",
    "artifact_sha256",
    "limitations",
}
_DATA_MANIFEST_FIELDS = set(
    "dataset_sha256 dataset_bytes dataset_rows contract_sha256 source_columns total_rows gap_count segments manifest_sha256".split()  # noqa: SIM905
)
_SEGMENT_FIELDS = set("segment_id path start end rows sha256".split())  # noqa: SIM905
_FEATURE_MANIFEST_FIELDS = set(
    "contract_sha256 data_manifest_sha256 feature_columns total_windows windows_by_split rejected_windows_by_reason output_path output_sha256 manifest_sha256".split()  # noqa: SIM905
)
_PUBLISHED_EVENT_FIELDS = set(
    "event_id evaluable matching_horizon_valid_decisions source_interval_valid_decisions source_interval_coverage_seconds detected first_detection_time lead_seconds_to_source_start lead_seconds_to_local_lps".split()  # noqa: SIM905
)
_PUBLISHED_EPISODE_FIELDS = set(
    "detection_time last_detection_time decision_count".split()  # noqa: SIM905
)
_PUBLISHED_EVALUATION_FIELDS = set(
    "threshold valid_holdout_decisions positive_decisions anomalous_decisions normal_valid_decisions normal_exposure_days time_in_alert pr_auc detected_events total_events false_episodes false_episodes_per_day event_results feasible".split()  # noqa: SIM905
)
_METRIC_FIELDS = _PUBLISHED_EVALUATION_FIELDS | {
    "fit_seconds",
    "score_seconds",
    "model_parameters",
}
_PARAMETER_FIELDS = {
    "statistical": {"robust_mad_scale", "aggregation"},
    "isolation_forest": {
        "n_estimators",
        "max_samples",
        "contamination",
        "random_state",
        "n_jobs",
        "score_rule",
    },
    "autoencoder": {
        "hidden_width",
        "bottleneck_width",
        "activation",
        "loss",
        "optimizer",
        "learning_rate",
        "batch_size",
        "epochs",
        "device",
        "deterministic",
        "num_workers",
        "scaler",
    },
}


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], value)


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    unknown = set(value).difference(expected)
    missing = expected.difference(value)
    if unknown:
        raise ValueError(f"{context} has unknown keys: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{context} is missing keys: {', '.join(sorted(missing))}")


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(dict[str, object], value)


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a list")
    return cast(list[object], value)


def _number(value: object, context: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{context} must be a finite number")
    return value


def _string(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string")
    return value


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be boolean")
    return value


def _validate_manifest_values(manifest: dict[str, object]) -> None:
    for key in ("schema_version", "run_id", "dataset_sha256", "contract_sha256", "git_sha"):
        _string(manifest[key], f"manifest.{key}")
    for key in ("python_version", "platform"):
        _string(manifest[key], f"manifest.{key}")
    _boolean(manifest["tracked_tree_clean"], "manifest.tracked_tree_clean")
    _number(manifest["window_seconds"], "manifest.window_seconds")
    _number(manifest["stride_seconds"], "manifest.stride_seconds")

    dependencies = _mapping(manifest["dependencies"], "manifest.dependencies")
    _exact_keys(dependencies, set(DEPENDENCIES), "manifest.dependencies")
    for name, dependency_version in dependencies.items():
        _string(dependency_version, f"manifest.dependencies.{name}")

    split_bounds = _mapping(manifest["split_bounds"], "manifest.split_bounds")
    _exact_keys(split_bounds, {"train", "calibration", "holdout"}, "manifest.split_bounds")
    for split_name, value in split_bounds.items():
        bounds = _mapping(value, f"manifest.split_bounds.{split_name}")
        _exact_keys(bounds, {"start", "end"}, f"manifest.split_bounds.{split_name}")
        _string(bounds["start"], f"manifest.split_bounds.{split_name}.start")
        _string(bounds["end"], f"manifest.split_bounds.{split_name}.end")

    for index, column in enumerate(_list(manifest["feature_columns"], "feature_columns")):
        _string(column, f"manifest.feature_columns[{index}]")
    for index, limitation in enumerate(_list(manifest["limitations"], "limitations")):
        _string(limitation, f"manifest.limitations[{index}]")

    evaluations = _mapping(manifest["holdout_evaluations"], "holdout_evaluations")
    _exact_keys(evaluations, set(MODEL_IDS), "manifest.holdout_evaluations")
    if any(value != 1 or isinstance(value, bool) for value in evaluations.values()):
        raise ValueError("manifest.holdout_evaluations must record one evaluation per model")


def _validate_parameters(value: object, context: str) -> dict[str, object]:
    parameters = _mapping(value, context)
    _exact_keys(parameters, set(MODEL_IDS), context)
    for model_id in MODEL_IDS:
        model_parameters = _mapping(parameters[model_id], f"{context}.{model_id}")
        _exact_keys(model_parameters, _PARAMETER_FIELDS[model_id], f"{context}.{model_id}")
        for name, parameter in model_parameters.items():
            if isinstance(parameter, (dict, list)) or parameter is None:
                raise ValueError(f"{context}.{model_id}.{name} must be scalar")
            if isinstance(parameter, float):
                _number(parameter, f"{context}.{model_id}.{name}")
    return parameters


def _validate_events(value: object, context: str) -> list[object]:
    events = _list(value, context)
    for index, item in enumerate(events):
        event_result = _mapping(item, f"{context}[{index}]")
        _exact_keys(event_result, _PUBLISHED_EVENT_FIELDS, f"{context}[{index}]")
        _string(event_result["event_id"], f"{context}[{index}].event_id")
        _boolean(event_result["evaluable"], f"{context}[{index}].evaluable")
        _boolean(event_result["detected"], f"{context}[{index}].detected")
        for key in (
            "matching_horizon_valid_decisions",
            "source_interval_valid_decisions",
            "source_interval_coverage_seconds",
        ):
            _number(event_result[key], f"{context}[{index}].{key}")
        for key in (
            "lead_seconds_to_source_start",
            "lead_seconds_to_local_lps",
        ):
            if event_result[key] is not None:
                _number(event_result[key], f"{context}[{index}].{key}")
        detection = event_result["first_detection_time"]
        if detection is not None:
            _string(detection, f"{context}[{index}].first_detection_time")
    return events


def _verify_embedded_manifest_hash(value: dict[str, object], context: str) -> None:
    stored_hash = value["manifest_sha256"]
    payload = {key: item for key, item in value.items() if key != "manifest_sha256"}
    encoded = _canonical_json(payload).encode("utf-8")
    if not isinstance(stored_hash, str) or hashlib.sha256(encoded).hexdigest() != stored_hash:
        raise ValueError(f"{context} embedded manifest SHA-256 mismatch")


def _validate_source_artifacts(
    run_dir: Path,
    manifest: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    artifact_hashes = _mapping(manifest["artifact_sha256"], "manifest.artifact_sha256")
    _exact_keys(artifact_hashes, set(ARTIFACT_NAMES), "manifest.artifact_sha256")
    for name, expected in artifact_hashes.items():
        if not isinstance(expected, str) or sha256_file(run_dir / name) != expected:
            raise ValueError(f"source artifact SHA-256 mismatch: {name}")

    data_manifest = _object(run_dir / "data_manifest.json")
    _exact_keys(data_manifest, _DATA_MANIFEST_FIELDS, "data_manifest.json")
    _verify_embedded_manifest_hash(data_manifest, "data manifest")
    for index, item in enumerate(_list(data_manifest["segments"], "data_manifest.segments")):
        segment = _mapping(item, f"data_manifest.segments[{index}]")
        _exact_keys(segment, _SEGMENT_FIELDS, f"data_manifest.segments[{index}]")

    feature_manifest = _object(run_dir / "feature_manifest.json")
    _exact_keys(feature_manifest, _FEATURE_MANIFEST_FIELDS, "feature_manifest.json")
    _verify_embedded_manifest_hash(feature_manifest, "feature manifest")
    return data_manifest, feature_manifest


def publish_aggregate_results(run_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    """Publish only schema-allowlisted aggregate evidence from hashed local artifacts."""
    run_dir = Path(run_dir)
    output_dir = Path(output_dir)
    manifest = _object(run_dir / "manifest.json")
    _exact_keys(manifest, _MANIFEST_FIELDS, "manifest.json")
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["run_id"] != run_dir.name:
        raise ValueError("benchmark manifest identity does not match its run directory")
    _validate_manifest_values(manifest)
    expected_run_id = (
        f"run-{cast(str, manifest['contract_sha256'])[:12]}-{cast(str, manifest['git_sha'])[:12]}"
    )
    if manifest["run_id"] != expected_run_id:
        raise ValueError("benchmark manifest run_id does not match contract and Git hashes")
    if manifest["tracked_tree_clean"] is not True:
        raise ValueError("aggregate publication requires a clean Git worktree")

    data_manifest, feature_manifest = _validate_source_artifacts(run_dir, manifest)
    if data_manifest["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("data manifest dataset identity disagrees with benchmark manifest")
    if data_manifest["contract_sha256"] != manifest["contract_sha256"]:
        raise ValueError("data manifest contract identity disagrees with benchmark manifest")
    if feature_manifest["contract_sha256"] != manifest["contract_sha256"]:
        raise ValueError("feature manifest contract identity disagrees with benchmark manifest")
    if feature_manifest["data_manifest_sha256"] != data_manifest["manifest_sha256"]:
        raise ValueError("feature manifest data manifest identity disagrees with prepared data")
    if feature_manifest["feature_columns"] != manifest["feature_columns"]:
        raise ValueError("feature manifest columns disagree with benchmark manifest")

    parameters = _validate_parameters(manifest["model_parameters"], "manifest.model_parameters")
    thresholds = _mapping(manifest["threshold_provenance"], "manifest.threshold_provenance")
    _exact_keys(thresholds, set(MODEL_IDS), "manifest.threshold_provenance")
    for model_id in MODEL_IDS:
        provenance = _mapping(thresholds[model_id], f"threshold_provenance.{model_id}")
        _exact_keys(
            provenance,
            {"split", "quantile", "method", "threshold"},
            f"threshold_provenance.{model_id}",
        )
        _string(provenance["split"], f"threshold_provenance.{model_id}.split")
        _string(provenance["method"], f"threshold_provenance.{model_id}.method")
        _number(provenance["quantile"], f"threshold_provenance.{model_id}.quantile")
        _number(provenance["threshold"], f"threshold_provenance.{model_id}.threshold")

    metrics = _object(run_dir / "metrics.json")
    events = _object(run_dir / "event_results.json")
    episodes = _object(run_dir / "episodes.json")
    for context, payload in (
        ("metrics", metrics),
        ("event_results", events),
        ("episodes", episodes),
    ):
        _exact_keys(payload, set(MODEL_IDS), context)

    aggregate_models: dict[str, object] = {}
    feasibility: dict[str, bool] = {}
    for model_id in MODEL_IDS:
        metric = _mapping(metrics[model_id], f"metrics.{model_id}")
        _exact_keys(metric, _METRIC_FIELDS, f"metrics.{model_id}")
        if metric["threshold"] != _mapping(thresholds[model_id], model_id)["threshold"]:
            raise ValueError(f"metrics.{model_id}.threshold disagrees with threshold provenance")
        for key in _PUBLISHED_EVALUATION_FIELDS.difference({"event_results", "feasible"}) | {
            "fit_seconds",
            "score_seconds",
        }:
            _number(metric[key], f"metrics.{model_id}.{key}")
        metric_parameters = _mapping(metric["model_parameters"], f"metrics.{model_id}.parameters")
        _exact_keys(
            metric_parameters,
            _PARAMETER_FIELDS[model_id],
            f"metrics.{model_id}.parameters",
        )
        if metric_parameters != parameters[model_id]:
            raise ValueError(f"metrics.{model_id} parameters disagree with manifest")
        event_results = _validate_events(events[model_id], f"event_results.{model_id}")
        metric_events = _validate_events(
            metric["event_results"],
            f"metrics.{model_id}.event_results",
        )
        if metric_events != event_results:
            raise ValueError(f"metrics.{model_id} event results disagree with source artifact")
        for index, item in enumerate(_list(episodes[model_id], f"episodes.{model_id}")):
            episode = _mapping(item, f"episodes.{model_id}[{index}]")
            _exact_keys(episode, _PUBLISHED_EPISODE_FIELDS, f"episodes.{model_id}[{index}]")
            _string(
                episode["detection_time"],
                f"episodes.{model_id}[{index}].detection_time",
            )
            _string(
                episode["last_detection_time"],
                f"episodes.{model_id}[{index}].last_detection_time",
            )
            _number(
                episode["decision_count"],
                f"episodes.{model_id}[{index}].decision_count",
            )

        feasible = metric["feasible"]
        if not isinstance(feasible, bool):
            raise ValueError(f"metrics.{model_id}.feasible must be boolean")
        feasibility[model_id] = feasible
        aggregate_models[model_id] = {
            "parameters": metric_parameters,
            "threshold": metric["threshold"],
            "metrics": {
                key: metric[key]
                for key in (
                    "time_in_alert",
                    "pr_auc",
                    "detected_events",
                    "total_events",
                    "false_episodes",
                    "false_episodes_per_day",
                )
            },
            "timings": {
                "fit_seconds": metric["fit_seconds"],
                "score_seconds": metric["score_seconds"],
            },
            "counts": {
                key: metric[key]
                for key in (
                    "valid_holdout_decisions",
                    "positive_decisions",
                    "anomalous_decisions",
                    "normal_valid_decisions",
                )
            },
            "normal_exposure_days": metric["normal_exposure_days"],
            "event_results": event_results,
            "feasible": feasible,
        }

    selected_model = next((model_id for model_id in MODEL_IDS if feasibility[model_id]), None)
    artifact_hashes = _mapping(manifest["artifact_sha256"], "manifest.artifact_sha256")
    aggregate: dict[str, object] = {
        "schema_version": manifest["schema_version"],
        "dataset_sha256": manifest["dataset_sha256"],
        "contract_sha256": manifest["contract_sha256"],
        "git_sha": manifest["git_sha"],
        "environment": {
            "python_version": manifest["python_version"],
            "platform": manifest["platform"],
            "dependencies": manifest["dependencies"],
        },
        "split_bounds": manifest["split_bounds"],
        "window": {
            "window_seconds": manifest["window_seconds"],
            "stride_seconds": manifest["stride_seconds"],
        },
        "feature_columns": manifest["feature_columns"],
        "models": aggregate_models,
        "feasibility_gate": feasibility,
        "selected_model": selected_model,
        "limitations": manifest["limitations"],
        "source_artifact_sha256": artifact_hashes,
    }

    json_path = output_dir / "phase1-benchmark.json"
    markdown_path = output_dir / "phase1-benchmark.md"
    if json_path.exists() or markdown_path.exists():
        raise FileExistsError("aggregate benchmark output already exists")
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(json_path, aggregate)

    models = cast(dict[str, object], aggregate["models"])
    lines = [
        "# Phase 1 Benchmark",
        "",
        f"Verdict: **{'FEASIBLE' if selected_model else 'NOT FEASIBLE'}**",
        f"Selected model: `{selected_model or 'none'}`",
        "",
        "| Model | Feasible | Events | False episodes/day | Time in alert | PR-AUC |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model_id in MODEL_IDS:
        model = cast(dict[str, object], models[model_id])
        model_metrics = cast(dict[str, object], model["metrics"])
        lines.append(
            f"| {model_id} | {model['feasible']} | "
            f"{model_metrics['detected_events']}/{model_metrics['total_events']} | "
            f"{model_metrics['false_episodes_per_day']} | {model_metrics['time_in_alert']} | "
            f"{model_metrics['pr_auc']} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in cast(list[str], aggregate["limitations"]))
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    arguments = parser.parse_args(argv)
    result = run_benchmark(
        dataset=arguments.dataset,
        work_dir=arguments.work_dir,
        artifact_dir=arguments.artifact_dir,
    )
    print(result.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
