from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
from tests.helpers import sample_contract, write_sample_csv

import industrial_reliability.benchmark as benchmark
from industrial_reliability.benchmark import publish_aggregate_results, run_benchmark
from industrial_reliability.contracts import PHASE1, Phase1Contract
from industrial_reliability.data import DataContractError, sha256_file
from industrial_reliability.evaluation import EvaluationResult

MODEL_IDS = ("statistical", "isolation_forest", "autoencoder")
GIB = 1024**3


def _benchmark_contract(source: Path) -> Phase1Contract:
    contract = sample_contract(source)
    return replace(
        contract,
        events=tuple(replace(event, source_precision="minute") for event in contract.events),
    )


def _sample_csv(path: Path, periods: int = 7_200) -> Path:
    timestamps = pd.date_range("2022-01-01 06:00:00", periods=periods, freq="s")
    write_sample_csv(path, [timestamp.to_pydatetime() for timestamp in timestamps])
    return path


def _forbidden_json_key(value: object) -> bool:
    forbidden = {"raw_rows", "feature_matrix", "features", "scores", "weights", "dataset_path"}
    if isinstance(value, dict):
        return bool(forbidden.intersection(value)) or any(
            _forbidden_json_key(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_forbidden_json_key(item) for item in value)
    return False


def _canonical_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def _embedded_manifest_hash(value: dict[str, object]) -> str:
    payload = {key: item for key, item in value.items() if key != "manifest_sha256"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_hashed_artifact(
    run_dir: Path,
    manifest: dict[str, Any],
    name: str,
    payload: dict[str, Any],
    *,
    update_embedded_hash: bool,
) -> None:
    if update_embedded_hash and "manifest_sha256" in payload:
        payload["manifest_sha256"] = _embedded_manifest_hash(payload)
    path = run_dir / name
    _canonical_json(path, payload)
    manifest["artifact_sha256"][name] = sha256_file(path)
    _canonical_json(run_dir / "manifest.json", manifest)


def _restore_hashed_artifact(
    run_dir: Path,
    manifest: dict[str, Any],
    name: str,
    original: bytes,
) -> None:
    path = run_dir / name
    path.write_bytes(original)
    manifest["artifact_sha256"][name] = sha256_file(path)
    _canonical_json(run_dir / "manifest.json", manifest)


def test_benchmark_writes_complete_reproducible_manifest_and_routes_splits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _sample_csv(tmp_path / "benchmark.csv")
    contract = _benchmark_contract(source)
    fit_inputs: dict[str, list[np.ndarray]] = {model_id: [] for model_id in MODEL_IDS}
    score_calls: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        model_id: [] for model_id in MODEL_IDS
    }
    scaler_means: list[np.ndarray] = []
    calibration_inputs: list[np.ndarray] = []
    evaluation_inputs: list[pd.DataFrame] = []
    monkeypatch.setattr(benchmark, "_git_provenance", lambda _: ("a" * 40, True))

    def fit_spy(model_id: str, original: Any) -> Any:
        def wrapped(detector: Any, values: np.ndarray) -> Any:
            fit_inputs[model_id].append(values.copy())
            fitted = original(detector, values)
            if model_id == "autoencoder":
                scaler_means.append(fitted.scaler_mean.copy())
            return fitted

        return wrapped

    def score_spy(model_id: str, original: Any) -> Any:
        def wrapped(detector: Any, values: np.ndarray) -> np.ndarray:
            scores = original(detector, values)
            score_calls[model_id].append((values.copy(), scores.copy()))
            return scores

        return wrapped

    for model_id, detector_type in (
        ("statistical", benchmark.RobustStatisticalDetector),
        ("isolation_forest", benchmark.IsolationForestDetector),
        ("autoencoder", benchmark.DenseAutoencoderDetector),
    ):
        monkeypatch.setattr(detector_type, "fit", fit_spy(model_id, detector_type.fit))
        monkeypatch.setattr(detector_type, "score", score_spy(model_id, detector_type.score))

    real_calibrate = benchmark.calibrate_threshold

    def calibrate_spy(values: np.ndarray, policy: Phase1Contract) -> float:
        calibration_inputs.append(np.asarray(values, dtype=np.float64).copy())
        return real_calibrate(values, policy)

    real_evaluate = benchmark.evaluate

    def evaluate_spy(*args: Any, **kwargs: Any) -> EvaluationResult:
        evaluation_inputs.append(args[0].copy())
        return real_evaluate(*args, **kwargs)

    monkeypatch.setattr(benchmark, "calibrate_threshold", calibrate_spy)
    monkeypatch.setattr(benchmark, "evaluate", evaluate_spy)

    first = run_benchmark(
        dataset=source,
        work_dir=tmp_path / "work-first",
        artifact_dir=tmp_path / "artifacts-first",
        contract=contract,
        autoencoder_epochs=1,
        require_clean_git=False,
    )
    repeat = run_benchmark(
        dataset=source,
        work_dir=tmp_path / "work-repeat",
        artifact_dir=tmp_path / "artifacts-repeat",
        contract=contract,
        autoencoder_epochs=1,
        require_clean_git=False,
    )

    changed_source = tmp_path / "benchmark-holdout-changed.csv"
    changed = pd.read_csv(source)
    holdout_mask = pd.to_datetime(changed["timestamp"]) >= contract.holdout.start
    changed.loc[holdout_mask, list(contract.analog_columns)] += 1_000_000.0
    changed.to_csv(changed_source, index=False, lineterminator="\n")
    changed_contract = _benchmark_contract(changed_source)
    holdout_changed = run_benchmark(
        dataset=changed_source,
        work_dir=tmp_path / "work-holdout-changed",
        artifact_dir=tmp_path / "artifacts-holdout-changed",
        contract=changed_contract,
        autoencoder_epochs=1,
        require_clean_git=False,
    )

    assert set(first.metrics) == set(MODEL_IDS)
    assert first.manifest["contract_sha256"]
    assert first.manifest["git_sha"]
    assert first.manifest["holdout_evaluations"] == dict.fromkeys(MODEL_IDS, 1)
    assert set(first.run_dir.iterdir()) == {
        first.run_dir / name
        for name in (
            "manifest.json",
            "data_manifest.json",
            "feature_manifest.json",
            "scores.parquet",
            "episodes.json",
            "event_results.json",
            "metrics.json",
            "limitations.md",
        )
    }
    assert (first.run_dir / "data_manifest.json").read_bytes() == (
        tmp_path / "work-first" / "prepared" / "manifest.json"
    ).read_bytes()
    assert (first.run_dir / "feature_manifest.json").read_bytes() == (
        tmp_path / "work-first" / "features.manifest.json"
    ).read_bytes()

    expected_metric_fields = {field.name for field in fields(EvaluationResult)} | {
        "fit_seconds",
        "score_seconds",
        "model_parameters",
    }
    for model_id in MODEL_IDS:
        assert set(first.metrics[model_id]) == expected_metric_fields
        assert (
            first.metrics[model_id]["event_results"]
            == json.loads((first.run_dir / "event_results.json").read_text(encoding="utf-8"))[
                model_id
            ]
        )

    scores = pd.read_parquet(first.run_dir / "scores.parquet")
    assert tuple(scores.columns) == (
        "window_start",
        "window_end",
        "split",
        "model_id",
        "raw_score",
        "threshold",
        "is_anomaly",
    )
    assert set(scores["model_id"]) == set(MODEL_IDS)
    assert set(scores["split"]) == {"holdout"}

    artifact_hashes = first.manifest["artifact_sha256"]
    assert set(artifact_hashes) == {
        "data_manifest.json",
        "feature_manifest.json",
        "scores.parquet",
        "episodes.json",
        "event_results.json",
        "metrics.json",
        "limitations.md",
    }
    assert all(
        sha256_file(first.run_dir / name) == digest for name, digest in artifact_hashes.items()
    )
    for name in (
        "manifest.json",
        "data_manifest.json",
        "feature_manifest.json",
        "episodes.json",
        "event_results.json",
        "metrics.json",
    ):
        assert not _forbidden_json_key(
            json.loads((first.run_dir / name).read_text(encoding="utf-8"))
        )

    feature_frame = pd.read_parquet(tmp_path / "work-first" / "features.parquet")
    expected_by_split = {
        split: frame.loc[:, contract.feature_columns].to_numpy(dtype=np.float64)
        for split, frame in feature_frame.groupby("split", sort=False)
    }
    for model_index, model_id in enumerate(MODEL_IDS):
        assert len(fit_inputs[model_id]) == 3
        assert len(score_calls[model_id]) == 6
        np.testing.assert_array_equal(fit_inputs[model_id][0], expected_by_split["train"])
        np.testing.assert_array_equal(score_calls[model_id][0][0], expected_by_split["calibration"])
        np.testing.assert_array_equal(score_calls[model_id][1][0], expected_by_split["holdout"])
        np.testing.assert_array_equal(calibration_inputs[model_index], score_calls[model_id][0][1])
        pd.testing.assert_series_equal(
            evaluation_inputs[model_index]["window_end"].reset_index(drop=True),
            feature_frame.loc[feature_frame["split"] == "holdout", "window_end"].reset_index(
                drop=True
            ),
            check_names=False,
        )

    assert len(calibration_inputs) == 9
    assert len(evaluation_inputs) == 9
    np.testing.assert_array_equal(scaler_means[0], scaler_means[1])
    np.testing.assert_array_equal(scaler_means[0], scaler_means[2])
    for model_id in MODEL_IDS:
        first_threshold = first.manifest["threshold_provenance"][model_id]["threshold"]
        assert repeat.manifest["threshold_provenance"][model_id]["threshold"] == pytest.approx(
            first_threshold
        )
        assert holdout_changed.manifest["threshold_provenance"][model_id][
            "threshold"
        ] == pytest.approx(first_threshold)

    stable_fields = {field.name for field in fields(EvaluationResult)}
    for model_id in ("statistical", "isolation_forest"):
        assert {key: first.metrics[model_id][key] for key in stable_fields} == {
            key: repeat.metrics[model_id][key] for key in stable_fields
        }

    aggregate_json, aggregate_markdown = publish_aggregate_results(
        first.run_dir,
        tmp_path / "published",
    )
    aggregate = json.loads(aggregate_json.read_text(encoding="utf-8"))
    assert set(aggregate) == {
        "schema_version",
        "dataset_sha256",
        "contract_sha256",
        "git_sha",
        "environment",
        "split_bounds",
        "window",
        "feature_columns",
        "models",
        "feasibility_gate",
        "selected_model",
        "limitations",
        "source_artifact_sha256",
    }
    assert aggregate_markdown.read_text(encoding="utf-8").startswith("# Phase 1 Benchmark")
    assert not _forbidden_json_key(aggregate)

    manifest_path = first.run_dir / "manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    manifest_payload["tracked_tree_clean"] = False
    _canonical_json(manifest_path, manifest_payload)
    with pytest.raises(ValueError, match=r"clean.*worktree"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-dirty")
    manifest_payload["tracked_tree_clean"] = True
    _canonical_json(manifest_path, manifest_payload)

    manifest_payload["git_sha"] = "b" * 40
    _canonical_json(manifest_path, manifest_payload)
    with pytest.raises(ValueError, match="run_id"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-run-id")
    manifest_payload["git_sha"] = "a" * 40
    _canonical_json(manifest_path, manifest_payload)

    data_path = first.run_dir / "data_manifest.json"
    original_data = data_path.read_bytes()
    data_payload = json.loads(original_data)
    data_payload["total_rows"] += 1
    _write_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "data_manifest.json",
        data_payload,
        update_embedded_hash=False,
    )
    with pytest.raises(ValueError, match=r"data.*manifest.*SHA-256"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-data-self-hash")
    _restore_hashed_artifact(first.run_dir, manifest_payload, "data_manifest.json", original_data)

    feature_path = first.run_dir / "feature_manifest.json"
    original_feature = feature_path.read_bytes()
    feature_payload = json.loads(original_feature)
    feature_payload["total_windows"] += 1
    _write_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "feature_manifest.json",
        feature_payload,
        update_embedded_hash=False,
    )
    with pytest.raises(ValueError, match=r"feature.*manifest.*SHA-256"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-feature-self-hash")
    _restore_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "feature_manifest.json",
        original_feature,
    )

    feature_payload = json.loads(original_feature)
    feature_payload["contract_sha256"] = "c" * 64
    _write_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "feature_manifest.json",
        feature_payload,
        update_embedded_hash=True,
    )
    with pytest.raises(ValueError, match=r"feature.*contract"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-feature-contract")
    _restore_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "feature_manifest.json",
        original_feature,
    )

    feature_payload = json.loads(original_feature)
    feature_payload["data_manifest_sha256"] = "d" * 64
    _write_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "feature_manifest.json",
        feature_payload,
        update_embedded_hash=True,
    )
    with pytest.raises(ValueError, match=r"feature.*data manifest"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-feature-data")
    _restore_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "feature_manifest.json",
        original_feature,
    )

    metrics_path = first.run_dir / "metrics.json"
    original_metrics = metrics_path.read_bytes()
    metrics_payload = json.loads(original_metrics)
    metrics_payload["statistical"]["threshold"] += 1.0
    _write_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "metrics.json",
        metrics_payload,
        update_embedded_hash=False,
    )
    with pytest.raises(ValueError, match=r"threshold.*provenance"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-threshold")
    _restore_hashed_artifact(first.run_dir, manifest_payload, "metrics.json", original_metrics)

    reflected_event_fields = getattr(benchmark, "_EVENT_RESULT_FIELDS", set())
    monkeypatch.setattr(
        benchmark,
        "_EVENT_RESULT_FIELDS",
        {*reflected_event_fields, "secret_path"},
        raising=False,
    )
    events_path = first.run_dir / "event_results.json"
    original_events = events_path.read_bytes()
    events_payload = json.loads(original_events)
    metrics_payload = json.loads(original_metrics)
    for model_id in MODEL_IDS:
        for event in events_payload[model_id]:
            event["secret_path"] = "raw-like-secret"
        for event in metrics_payload[model_id]["event_results"]:
            event["secret_path"] = "raw-like-secret"
    _write_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "event_results.json",
        events_payload,
        update_embedded_hash=False,
    )
    _write_hashed_artifact(
        first.run_dir,
        manifest_payload,
        "metrics.json",
        metrics_payload,
        update_embedded_hash=False,
    )
    with pytest.raises(ValueError, match=r"unknown.*secret_path"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-future-event-field")
    _restore_hashed_artifact(first.run_dir, manifest_payload, "event_results.json", original_events)
    _restore_hashed_artifact(first.run_dir, manifest_payload, "metrics.json", original_metrics)

    metrics_payload = json.loads(original_metrics)
    metrics_payload["statistical"]["raw_rows"] = [["must", "not", "publish"]]
    _canonical_json(metrics_path, metrics_payload)
    manifest_payload["artifact_sha256"]["metrics.json"] = sha256_file(metrics_path)
    _canonical_json(manifest_path, manifest_payload)
    with pytest.raises(ValueError, match=r"unknown.*raw_rows"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-publication")

    del metrics_payload["statistical"]["raw_rows"]
    _canonical_json(metrics_path, metrics_payload)
    manifest_payload["artifact_sha256"]["metrics.json"] = sha256_file(metrics_path)
    manifest_payload["dependencies"]["secret_path"] = str(tmp_path / "private")
    _canonical_json(manifest_path, manifest_payload)
    with pytest.raises(ValueError, match=r"unknown.*secret_path"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-secret")

    del manifest_payload["dependencies"]["secret_path"]
    metrics_payload["statistical"]["pr_auc"] = {"raw_rows": []}
    _canonical_json(metrics_path, metrics_payload)
    manifest_payload["artifact_sha256"]["metrics.json"] = sha256_file(metrics_path)
    _canonical_json(manifest_path, manifest_payload)
    with pytest.raises(ValueError, match=r"pr_auc.*number"):
        publish_aggregate_results(first.run_dir, tmp_path / "rejected-nonscalar")


def test_benchmark_rejects_low_disk_before_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preparation_called = False

    def prepare_not_expected(*args: object, **kwargs: object) -> None:
        nonlocal preparation_called
        preparation_called = True

    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=11 * GIB, free=10 * GIB - 1),
    )
    monkeypatch.setattr(benchmark, "prepare_dataset", prepare_not_expected)

    with pytest.raises(RuntimeError, match="10 GiB"):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work",
            tmp_path / "artifacts",
            contract=replace(PHASE1, dataset_sha256="fixture"),
            autoencoder_epochs=1,
            require_clean_git=False,
        )

    assert preparation_called is False


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def test_clean_tree_allows_only_untracked_codex_descendants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    codex_file = repo / ".codex" / "rules" / "local.md"
    codex_file.parent.mkdir(parents=True)
    codex_file.write_text("local only\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=1 * GIB, free=19 * GIB),
    )

    with pytest.raises(FileNotFoundError):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work-allowed",
            tmp_path / "artifacts",
        )

    rogue = repo / "src" / "rogue.py"
    rogue.parent.mkdir()
    rogue.write_text("ROGUE = True\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"src/rogue\.py"):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work-rejected",
            tmp_path / "artifacts",
        )


def test_benchmark_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    source = _sample_csv(tmp_path / "source.csv", periods=180)
    contract = _benchmark_contract(source)
    source.write_text(source.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(DataContractError, match=r"byte count|SHA-256"):
        run_benchmark(
            source,
            tmp_path / "work",
            tmp_path / "artifacts",
            contract=contract,
            autoencoder_epochs=1,
            require_clean_git=False,
        )


def test_benchmark_rejects_missing_split_windows(tmp_path: Path) -> None:
    source = _sample_csv(tmp_path / "short.csv", periods=180)

    with pytest.raises(ValueError, match=r"calibration.*holdout|missing.*split"):
        run_benchmark(
            source,
            tmp_path / "work",
            tmp_path / "artifacts",
            contract=_benchmark_contract(source),
            autoencoder_epochs=1,
            require_clean_git=False,
        )


def test_benchmark_rejects_stale_work_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "stale.txt").write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=1 * GIB, free=19 * GIB),
    )

    with pytest.raises(FileExistsError, match="nonempty"):
        run_benchmark(
            tmp_path / "missing.csv",
            work_dir,
            tmp_path / "artifacts",
            contract=replace(PHASE1, dataset_sha256="fixture"),
            autoencoder_epochs=1,
            require_clean_git=False,
        )


def test_full_contract_rejects_epoch_override_before_dataset_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=1 * GIB, free=19 * GIB),
    )

    with pytest.raises(ValueError, match="epoch override"):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work",
            tmp_path / "artifacts",
            autoencoder_epochs=1,
            require_clean_git=False,
        )

    with pytest.raises(ValueError, match="epoch override"):
        run_benchmark(
            tmp_path / "copied-full-dataset.csv",
            tmp_path / "work-copy",
            tmp_path / "artifacts-copy",
            contract=replace(PHASE1, dataset_path="copied-full-dataset.csv"),
            autoencoder_epochs=1,
            require_clean_git=False,
        )


@pytest.mark.parametrize("override", [None, 1])
def test_full_identity_rejects_mutated_contract_epochs_before_dataset_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override: int | None,
) -> None:
    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=1 * GIB, free=19 * GIB),
    )

    with pytest.raises(ValueError, match="model settings"):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work",
            tmp_path / "artifacts",
            contract=replace(PHASE1, autoencoder_epochs=1),
            autoencoder_epochs=override,
            require_clean_git=False,
        )


@pytest.mark.parametrize("override", [None, 20])
def test_full_identity_rejects_float_contract_epochs_before_dataset_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override: int | None,
) -> None:
    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=1 * GIB, free=19 * GIB),
    )

    with pytest.raises(ValueError, match="positive built-in int"):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work",
            tmp_path / "artifacts",
            contract=replace(PHASE1, autoencoder_epochs=20.0),  # type: ignore[arg-type]
            autoencoder_epochs=override,
            require_clean_git=False,
        )


@pytest.mark.parametrize("override", [20.0, True])
def test_full_identity_rejects_non_integer_effective_epochs_before_dataset_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override: object,
) -> None:
    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=1 * GIB, free=19 * GIB),
    )

    with pytest.raises(ValueError, match="positive built-in int"):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work",
            tmp_path / "artifacts",
            autoencoder_epochs=override,  # type: ignore[arg-type]
            require_clean_git=False,
        )


@pytest.mark.parametrize(
    ("field_name", "equivalent_value"),
    [
        ("random_seed", 42.0),
        ("isolation_forest_estimators", 200.0),
        ("isolation_forest_n_jobs", True),
        ("autoencoder_hidden_width", 64.0),
        ("autoencoder_bottleneck_width", 16.0),
        ("autoencoder_batch_size", 256.0),
        ("autoencoder_deterministic", 1),
        ("autoencoder_num_workers", False),
    ],
)
def test_runner_rejects_python_equal_model_setting_types_before_dataset_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    equivalent_value: object,
) -> None:
    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=1 * GIB, free=19 * GIB),
    )

    with pytest.raises(ValueError, match="model settings"):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work",
            tmp_path / "artifacts",
            contract=replace(PHASE1, **{field_name: equivalent_value}),
            require_clean_git=False,
        )


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("random_seed", 7),
        ("robust_mad_scale", 1.0),
        ("statistical_aggregation", "mean_abs_robust_z"),
        ("isolation_forest_estimators", 10),
        ("isolation_forest_max_samples", "changed"),
        ("isolation_forest_contamination", "changed"),
        ("isolation_forest_n_jobs", 2),
        ("isolation_forest_score_rule", "score_samples"),
        ("autoencoder_hidden_width", 32),
        ("autoencoder_bottleneck_width", 8),
        ("autoencoder_activation", "tanh"),
        ("autoencoder_loss", "mae"),
        ("autoencoder_optimizer", "sgd"),
        ("autoencoder_learning_rate", 0.01),
        ("autoencoder_batch_size", 128),
        ("autoencoder_epochs", 1),
        ("autoencoder_scaler", "none"),
        ("autoencoder_device", "cuda"),
        ("autoencoder_deterministic", False),
        ("autoencoder_num_workers", 1),
    ],
)
def test_runner_rejects_non_phase1_hardcoded_model_settings_before_dataset_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    changed_value: object,
) -> None:
    monkeypatch.setattr(
        benchmark.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=20 * GIB, used=1 * GIB, free=19 * GIB),
    )

    with pytest.raises(ValueError, match="model settings"):
        run_benchmark(
            tmp_path / "missing.csv",
            tmp_path / "work",
            tmp_path / "artifacts",
            contract=replace(PHASE1, **{field_name: changed_value}),
            require_clean_git=False,
        )


def test_cli_parses_the_reproducible_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def run_spy(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(run_dir=tmp_path / "artifacts" / "run-id")

    monkeypatch.setattr(benchmark, "run_benchmark", run_spy)

    assert (
        benchmark.main(
            [
                "--dataset",
                "data/raw/metropt/dataset_train.csv",
                "--work-dir",
                "data/interim/phase1",
                "--artifact-dir",
                "artifacts/phase1",
            ]
        )
        == 0
    )
    assert captured == {
        "dataset": Path("data/raw/metropt/dataset_train.csv"),
        "work_dir": Path("data/interim/phase1"),
        "artifact_dir": Path("artifacts/phase1"),
    }
    assert "run-id" in capsys.readouterr().out


@pytest.mark.slow
def test_full_dataset_contract() -> None:
    source = Path("data/raw/metropt/dataset_train.csv")
    if not source.exists():
        pytest.skip("local MetroPT dataset unavailable")
    assert sha256_file(source) == PHASE1.dataset_sha256
