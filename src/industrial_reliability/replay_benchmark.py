from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from industrial_reliability.decision_gate import (
    ReplayBenchmarkResultV1,
    ReplayBenchmarkResultV2,
    ReplayBenchmarkSampleV1,
)
from industrial_reliability.report_hashes import require_committed_git_sha, resolve_git_sha


@dataclass(frozen=True, slots=True)
class ReplayBenchmarkConfig:
    workload_path: Path
    range_start: str
    range_end: str
    speed: int
    repetitions: int
    restart_repetition: int
    git_sha: str
    package_manifest: Path
    package_sha256: str
    contract_sha256: str
    source_dataset_sha256: str
    workload_sha256: str
    api_url: str
    prometheus_url: str
    output_dir: Path


def _require_sha(name: str, value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read JSON file: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _load_workload(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    expected = {
        "schema_version",
        "range_start",
        "range_end",
        "speed",
        "repetitions",
        "restart_repetition",
    }
    if set(data) != expected or data["schema_version"] != "replay-workload-v1":
        raise ValueError("replay-workload-v1 with the exact required fields is required")
    try:
        start = datetime.fromisoformat(str(data["range_start"]))
        end = datetime.fromisoformat(str(data["range_end"]))
    except ValueError as exc:
        raise ValueError("workload range timestamps must be ISO-8601") from exc
    if start >= end:
        raise ValueError("workload range_start must precede range_end")
    speed = data["speed"]
    repetitions = data["repetitions"]
    restart_repetition = data["restart_repetition"]
    if (
        not isinstance(speed, int)
        or isinstance(speed, bool)
        or speed <= 0
        or not isinstance(repetitions, int)
        or isinstance(repetitions, bool)
        or repetitions <= 0
        or not isinstance(restart_repetition, int)
        or isinstance(restart_repetition, bool)
        or not 1 <= restart_repetition <= repetitions
    ):
        raise ValueError("workload speed/repetition values are invalid")
    return data


def _verify_manifest(path: Path) -> tuple[str, str, str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"package manifest not found: {path}")
    data = _read_json(path)
    if data.get("schema_version") != "champion-package-v2":
        raise ValueError("champion-package-v2 manifest required")
    package_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    contract_sha = _require_sha("contract_sha256", data.get("contract_sha256"))
    dataset_sha = _require_sha("source_dataset_sha256", data.get("source_dataset_sha256"))
    artifacts = data.get("artifact_sha256")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("package manifest artifact_sha256 is required")
    for relative_name, expected_sha in artifacts.items():
        if not isinstance(relative_name, str) or not isinstance(expected_sha, str):
            raise ValueError("package artifact identities must be strings")
        _require_sha(f"artifact_sha256[{relative_name}]", expected_sha)
        artifact_path = path.parent / relative_name
        if not artifact_path.is_file():
            raise FileNotFoundError(f"package artifact not found: {artifact_path}")
        actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            raise ValueError(f"package artifact SHA-256 mismatch: {relative_name}")
    return package_sha, contract_sha, dataset_sha, str(data.get("model_version", ""))


def _committed_workload_bytes(git_sha: str) -> bytes:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "show", f"{git_sha}:ops/benchmarks/replay-workload.json"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("frozen benchmark workload is unavailable at supplied git SHA") from exc
    return result.stdout


def _verify_frozen_workload(workload_path: Path, git_sha: str) -> None:
    expected_workload = (
        Path(__file__).resolve().parents[2] / "ops" / "benchmarks" / "replay-workload.json"
    ).resolve()
    resolved_workload = workload_path.resolve()
    if resolved_workload != expected_workload:
        raise ValueError(f"frozen benchmark workload required: {expected_workload}")
    try:
        actual_workload = resolved_workload.read_bytes()
    except OSError as exc:
        raise ValueError(f"frozen benchmark workload is unreadable: {resolved_workload}") from exc
    if actual_workload != _committed_workload_bytes(git_sha):
        raise ValueError("frozen benchmark workload does not match supplied git SHA")


def build_benchmark_config(
    *,
    workload_path: Path,
    git_sha: str,
    package_manifest: Path,
    api_url: str,
    prometheus_url: str,
    output_dir: Path,
) -> ReplayBenchmarkConfig:
    require_committed_git_sha(git_sha)
    _verify_frozen_workload(workload_path, git_sha)

    workload = _load_workload(workload_path)
    package_sha, contract_sha, dataset_sha, model_version = _verify_manifest(package_manifest)
    if not model_version:
        raise ValueError("package manifest model_version is required")
    workload_sha = hashlib.sha256(workload_path.read_bytes()).hexdigest()
    return ReplayBenchmarkConfig(
        workload_path=workload_path.resolve(),
        range_start=str(workload["range_start"]),
        range_end=str(workload["range_end"]),
        speed=int(workload["speed"]),
        repetitions=int(workload["repetitions"]),
        restart_repetition=int(workload["restart_repetition"]),
        git_sha=git_sha,
        package_manifest=package_manifest.resolve(),
        package_sha256=package_sha,
        contract_sha256=contract_sha,
        source_dataset_sha256=dataset_sha,
        workload_sha256=workload_sha,
        api_url=api_url.rstrip("/"),
        prometheus_url=prometheus_url.rstrip("/"),
        output_dir=output_dir.resolve(),
    )


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP {response.status} from runtime endpoint")
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"runtime endpoint unavailable: {url}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"runtime endpoint returned a non-object: {url}")
    return data


def _prometheus_value(base_url: str, query: str, timeout_seconds: float = 10.0) -> float:
    url = f"{base_url}/api/v1/query?query={quote(query, safe='')}"
    data = _request_json(url, timeout_seconds=timeout_seconds)
    if data.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    result = data.get("data", {}).get("result")
    if not isinstance(result, list) or not result:
        raise RuntimeError(f"Prometheus query returned no samples: {query}")
    value = result[0].get("value") if isinstance(result[0], dict) else None
    if not isinstance(value, list) or len(value) != 2:
        raise RuntimeError(f"Prometheus query returned an invalid sample: {query}")
    try:
        parsed = float(value[1])
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Prometheus sample is not numeric: {query}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise RuntimeError(f"Prometheus sample is invalid: {query}")
    return parsed


def _prometheus_snapshot(
    base_url: str,
    *,
    include_latency: bool = True,
) -> dict[str, float]:
    queries = {
        "accepted": 'sum(irp_telemetry_events_total{outcome="accepted"})',
        "duplicate": 'sum(irp_telemetry_events_total{outcome="duplicate"})',
        "quarantine": 'sum(irp_telemetry_events_total{outcome="quarantined"})',
        "valid_windows": "sum(irp_valid_windows_total)",
        "score_ok": 'sum(irp_score_requests_total{outcome="ok"})',
        "anomaly": "sum(irp_anomaly_decisions_total)",
        "alerts": 'sum(irp_alert_events_total{action="opened"})',
        "lag": "max(irp_kafka_consumer_lag)",
        "feature_psi": "max(irp_feature_psi_max)",
        "latency_p50": (
            "histogram_quantile(0.50, sum(rate(irp_score_latency_seconds_bucket[5m])) by (le))"
        ),
        "latency_p95": (
            "histogram_quantile(0.95, sum(rate(irp_score_latency_seconds_bucket[5m])) by (le))"
        ),
    }
    if not include_latency:
        queries.pop("latency_p50")
        queries.pop("latency_p95")
    return {name: _prometheus_value(base_url, query) for name, query in queries.items()}


def _parse_bytes(value: str) -> int:
    units = {
        "B": 1,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
    }
    parts = value.strip().split()
    if len(parts) != 2 or parts[1] not in units:
        raise ValueError(f"invalid Docker memory value: {value!r}")
    parsed = float(parts[0]) * units[parts[1]]
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"invalid Docker memory value: {value!r}")
    return int(parsed)


def _parse_cpu_percent(value: str) -> float:
    if not value.strip().endswith("%"):
        raise ValueError(f"invalid Docker CPU value: {value!r}")
    parsed = float(value.strip()[:-1])
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"invalid Docker CPU value: {value!r}")
    return parsed


def _docker_stats_sample(service: str = "streaming-worker") -> dict[str, Any]:
    container_id = subprocess.run(
        ["docker", "compose", "ps", "-q", service],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not container_id:
        raise RuntimeError(f"Docker service has no running container: {service}")
    raw = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_id],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not raw:
        raise RuntimeError(f"Docker stats returned no sample for {service}")
    try:
        data = json.loads(raw)
        cpu_percent = _parse_cpu_percent(str(data["CPUPerc"]))
        memory_text = str(data["MemUsage"]).split("/", 1)[0]
        memory_bytes = _parse_bytes(memory_text)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Docker stats returned an invalid sample") from exc
    return {
        "observed_at": datetime.now(UTC).isoformat(),
        "service": service,
        "container_id": container_id,
        "cpu_percent": cpu_percent,
        "memory_bytes": memory_bytes,
    }


def _integrate_cpu_seconds(samples: Sequence[dict[str, Any]]) -> float:
    if len(samples) < 2:
        return 0.0
    total = 0.0
    for previous, current in pairwise(samples):
        previous_time = datetime.fromisoformat(str(previous["observed_at"]))
        current_time = datetime.fromisoformat(str(current["observed_at"]))
        elapsed = (current_time - previous_time).total_seconds()
        if elapsed < 0:
            raise ValueError("container observation timestamps must be ordered")
        total += (
            (float(previous["cpu_percent"]) + float(current["cpu_percent"])) / 2.0 / 100.0 * elapsed
        )
    return total


@dataclass(frozen=True, slots=True)
class _RuntimeRepetition:
    sample: ReplayBenchmarkSampleV1
    feature_digest: str
    score_digest: str
    alert_digest: str


def _require_success_data(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    data = payload.get("data")
    if payload.get("success") is not True or not isinstance(data, dict):
        raise RuntimeError(f"{operation} did not return a successful data envelope")
    return data


def _counter_delta(
    before: dict[str, float],
    after: dict[str, float],
    name: str,
) -> int:
    if name not in before or name not in after:
        raise RuntimeError(f"runtime metric is missing: {name}")
    delta = after[name] - before[name]
    if delta < 0:
        raise RuntimeError(f"runtime metric reset during repetition: {name}")
    return round(delta)


def _docker_restart_and_wait(config: ReplayBenchmarkConfig) -> float:
    started = time.perf_counter()
    try:
        subprocess.run(
            ["docker", "compose", "restart", "streaming-worker"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("streaming-worker restart failed") from exc

    deadline = started + 60.0
    while time.perf_counter() < deadline:
        try:
            health = _request_json(f"{config.api_url}/healthz", timeout_seconds=5.0)
            if health.get("success") is True:
                return round(time.perf_counter() - started, 3)
        except RuntimeError:
            pass
        time.sleep(0.5)
    raise RuntimeError("streaming-worker did not recover before the restart timeout")


def _fetch_replay_digests(
    config: ReplayBenchmarkConfig,
    replay_session_id: str,
) -> tuple[str, str, str]:
    alerts_data = _require_success_data(
        _request_json(f"{config.api_url}/v1/replays/{quote(replay_session_id, safe='')}/alerts"),
        "replay alerts",
    )
    alerts = alerts_data.get("alerts")
    if not isinstance(alerts, list):
        raise RuntimeError("replay alerts response did not contain an alerts list")

    feature_records: list[dict[str, Any]] = []
    score_records: list[dict[str, Any]] = []
    alert_records: list[dict[str, Any]] = []
    for alert in alerts:
        if not isinstance(alert, dict) or not isinstance(alert.get("alert_id"), str):
            raise RuntimeError("replay alerts response contained an invalid alert")
        alert_records.append(alert)
        detail_data = _require_success_data(
            _request_json(f"{config.api_url}/v1/alerts/{quote(alert['alert_id'], safe='')}"),
            "alert detail",
        )
        for key, target in (
            ("evidence", feature_records),
            ("decisions", score_records),
            ("events", alert_records),
        ):
            values = detail_data.get(key)
            if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
                raise RuntimeError(f"alert detail response contained invalid {key}")
            target.extend(values)

    return (
        compute_stream_digest(feature_records),
        compute_stream_digest(score_records),
        compute_stream_digest(alert_records),
    )


def _capture_repetition(
    config: ReplayBenchmarkConfig,
    repetition: int,
) -> _RuntimeRepetition:
    recovery_seconds = 0.0
    if repetition == config.restart_repetition:
        recovery_seconds = _docker_restart_and_wait(config)

    before_metrics = _prometheus_snapshot(config.prometheus_url, include_latency=False)
    containers: list[dict[str, Any]] = [_docker_stats_sample()]
    metric_snapshots: list[dict[str, float]] = [dict(before_metrics)]
    started = time.perf_counter()
    start_payload = _request_json(
        f"{config.api_url}/v1/replays",
        method="POST",
        payload={
            "range_start": config.range_start,
            "range_end": config.range_end,
            "speed": config.speed,
        },
    )
    replay_data = _require_success_data(start_payload, "replay start")
    replay_session_id = replay_data.get("replay_session_id")
    if not isinstance(replay_session_id, str) or not replay_session_id:
        raise RuntimeError("replay start did not return a session ID")

    deadline = started + 600.0
    completed_data: dict[str, Any] | None = None
    lag_samples: list[tuple[float, float]] = [(0.0, before_metrics["lag"])]
    while time.perf_counter() < deadline:
        current_metrics = _prometheus_snapshot(
            config.prometheus_url,
            include_latency=False,
        )
        metric_snapshots.append(dict(current_metrics))
        containers.append(_docker_stats_sample())
        lag_samples.append((time.perf_counter() - started, current_metrics["lag"]))
        status_data = _require_success_data(
            _request_json(f"{config.api_url}/v1/replays/{quote(replay_session_id, safe='')}"),
            "replay status",
        )
        state = status_data.get("state")
        if state == "COMPLETED":
            completed_data = status_data
            break
        if state == "FAILED":
            raise RuntimeError(f"replay session failed: {status_data.get('error_code', 'unknown')}")
        time.sleep(1.0)
    if completed_data is None:
        raise RuntimeError("replay session did not complete before the timeout")

    final_metrics = _prometheus_snapshot(config.prometheus_url)
    metric_snapshots.append(dict(final_metrics))
    containers.append(_docker_stats_sample())
    lag_samples.append((time.perf_counter() - started, final_metrics["lag"]))
    last_sequence = completed_data.get("last_sequence")
    if not isinstance(last_sequence, int) or last_sequence <= 0:
        raise RuntimeError("completed replay did not report a positive last_sequence")
    if (
        completed_data.get("source_dataset_sha256") != config.source_dataset_sha256
        or completed_data.get("contract_sha256") != config.contract_sha256
    ):
        raise RuntimeError("replay identity does not match the champion package")

    elapsed_seconds = time.perf_counter() - started
    if elapsed_seconds <= 0:
        raise RuntimeError("replay timing observation was not positive")
    positive_lag_seen = False
    lag_drain_seconds = 0.0
    positive_lag_started: float | None = None
    for observed_at, lag in lag_samples:
        if lag > 0.0 and positive_lag_started is None:
            positive_lag_started = observed_at
            positive_lag_seen = True
        elif positive_lag_started is not None and lag == 0.0:
            lag_drain_seconds = max(0.0, observed_at - positive_lag_started)
            break
    if positive_lag_seen and lag_drain_seconds == 0.0 and lag_samples[-1][1] > 0.0:
        raise RuntimeError("consumer lag did not drain to zero")

    feature_digest, score_digest, alert_digest = _fetch_replay_digests(
        config,
        replay_session_id,
    )
    source_events = last_sequence
    accepted = _counter_delta(before_metrics, final_metrics, "accepted")
    duplicate_rows = _counter_delta(before_metrics, final_metrics, "duplicate")
    quarantine_rows = _counter_delta(before_metrics, final_metrics, "quarantine")
    valid_windows = _counter_delta(before_metrics, final_metrics, "valid_windows")
    if accepted + duplicate_rows + quarantine_rows <= 0:
        raise RuntimeError("runtime replay produced no observed telemetry rows")
    recovery_passed = repetition != config.restart_repetition or recovery_seconds > 0.0
    timing_samples = (
        {
            "elapsed_seconds": round(elapsed_seconds, 6),
            "source_events": float(source_events),
            "valid_windows": float(valid_windows),
            "recovery_seconds": recovery_seconds,
        },
    )
    sample = ReplayBenchmarkSampleV1(
        repetition=repetition,
        source_events=source_events,
        valid_windows=valid_windows,
        p50_latency_ms=final_metrics["latency_p50"] * 1000.0,
        p95_latency_ms=final_metrics["latency_p95"] * 1000.0,
        throughput_events_per_second=source_events / elapsed_seconds,
        max_consumer_lag=max(lag for _, lag in lag_samples),
        lag_drain_seconds=lag_drain_seconds,
        duplicate_rows=duplicate_rows,
        quarantine_rows=quarantine_rows,
        cpu_seconds=_integrate_cpu_seconds(containers),
        peak_rss_bytes=max(int(item["memory_bytes"]) for item in containers),
        recovery_passed=recovery_passed,
        timing_samples=timing_samples,
        prometheus_samples=tuple(metric_snapshots),
        container_samples=tuple(containers),
    )
    return _RuntimeRepetition(
        sample=sample,
        feature_digest=feature_digest,
        score_digest=score_digest,
        alert_digest=alert_digest,
    )


def compute_stream_digest(records: list[dict[str, Any]]) -> str:
    hasher = hashlib.sha256()
    for rec in records:
        canonical = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("utf-8")
        hasher.update(canonical)
    return hasher.hexdigest()


def percentile(values: Sequence[float], quantile: float) -> float:
    """Deterministic linear interpolation percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(float(ordered[lower]), 3)
    weight = position - lower
    return round(float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight), 3)


def compute_latency_percentiles(samples_ms: Sequence[float]) -> tuple[float, float]:
    if not samples_ms:
        return (0.0, 0.0)
    p50 = percentile(samples_ms, 0.5)
    p95 = percentile(samples_ms, 0.95)
    return (p50, p95)


def aggregate_runtime_samples(
    config: ReplayBenchmarkConfig,
    repetitions: Sequence[_RuntimeRepetition],
    *,
    implementation: str = "python-worker",
) -> ReplayBenchmarkResultV2:
    """Aggregate captured runtime repetitions without introducing estimates."""
    if len(repetitions) != config.repetitions:
        raise ValueError("captured repetitions do not match the frozen workload")
    samples = tuple(item.sample for item in repetitions)
    if not all(sample.recovery_passed for sample in samples):
        raise RuntimeError("restart recovery was not observed for every required repetition")

    total_events = sum(sample.source_events for sample in samples)
    total_windows = sum(sample.valid_windows for sample in samples)
    total_duplicates = sum(sample.duplicate_rows for sample in samples)
    total_quarantines = sum(sample.quarantine_rows for sample in samples)
    p50_latency = percentile([sample.p50_latency_ms for sample in samples], 0.5)
    p95_latency = percentile([sample.p95_latency_ms for sample in samples], 0.95)
    throughput = sum(sample.throughput_events_per_second for sample in samples) / len(samples)
    max_lag = max(sample.max_consumer_lag for sample in samples)
    lag_drain = sum(sample.lag_drain_seconds for sample in samples) / len(samples)
    total_cpu_seconds = sum(float(sample.cpu_seconds) for sample in samples)
    cpu_per_million = total_cpu_seconds / total_events * 1_000_000.0 if total_events > 0 else 0.0
    feature_digest = compute_stream_digest(
        [
            {"repetition": item.sample.repetition, "digest": item.feature_digest}
            for item in repetitions
        ]
    )
    score_digest = compute_stream_digest(
        [
            {"repetition": item.sample.repetition, "digest": item.score_digest}
            for item in repetitions
        ]
    )
    alert_digest = compute_stream_digest(
        [
            {"repetition": item.sample.repetition, "digest": item.alert_digest}
            for item in repetitions
        ]
    )
    return ReplayBenchmarkResultV2(
        schema_version="replay-benchmark-v2",
        evidence_level="RUNTIME",
        implementation=implementation,
        git_sha=config.git_sha,
        champion_sha256=config.package_sha256,
        contract_sha256=config.contract_sha256,
        source_dataset_sha256=config.source_dataset_sha256,
        workload_sha256=config.workload_sha256,
        repetitions=len(samples),
        raw_samples=samples,
        source_events=total_events,
        valid_windows=total_windows,
        feature_digest=feature_digest,
        score_digest=score_digest,
        alert_digest=alert_digest,
        duplicate_rows=total_duplicates,
        quarantine_rows=total_quarantines,
        p50_latency_ms=p50_latency,
        p95_latency_ms=p95_latency,
        throughput_events_per_second=round(throughput, 2),
        max_consumer_lag=round(max_lag, 2),
        lag_drain_seconds=round(lag_drain, 3),
        cpu_seconds_per_million_events=round(cpu_per_million, 2),
        peak_rss_bytes=max(sample.peak_rss_bytes for sample in samples),
        restart_recovery_passed=True,
    ).with_computed_hash()


def run_benchmark(
    config: ReplayBenchmarkConfig,
    *,
    implementation: str = "python-worker",
) -> ReplayBenchmarkResultV2:
    captured = [
        _capture_repetition(config, repetition) for repetition in range(1, config.repetitions + 1)
    ]
    return aggregate_runtime_samples(
        config,
        captured,
        implementation=implementation,
    )


def write_runtime_result(result: ReplayBenchmarkResultV2, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "benchmark.json"
    temporary = output.with_name(f"{output.name}.tmp")
    temporary.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    temporary.replace(output)
    return output


def aggregate_samples(
    *,
    git_sha: str,
    package_sha256: str,
    contract_sha256: str,
    source_dataset_sha256: str,
    workload_sha256: str,
    samples: Sequence[ReplayBenchmarkSampleV1],
    implementation: str = "python-worker",
    feature_digest: str,
    score_digest: str,
    alert_digest: str,
) -> ReplayBenchmarkResultV1:
    """Aggregate raw repetition samples into a recomputable summary."""
    if not samples:
        raise ValueError("At least one sample is required to aggregate benchmark results")

    total_events = sum(s.source_events for s in samples)
    total_windows = sum(s.valid_windows for s in samples)
    total_dupes = sum(s.duplicate_rows for s in samples)
    total_quarantines = sum(s.quarantine_rows for s in samples)
    all_recovery_passed = all(s.recovery_passed for s in samples)

    p50_latencies = [s.p50_latency_ms for s in samples]
    p95_latencies = [s.p95_latency_ms for s in samples]
    throughputs = [s.throughput_events_per_second for s in samples]
    lags = [s.max_consumer_lag for s in samples]
    drain_times = [s.lag_drain_seconds for s in samples]
    cpu_secs = [s.cpu_seconds for s in samples]
    peak_rss = max(s.peak_rss_bytes for s in samples)

    agg_p50 = percentile(p50_latencies, 0.5)
    agg_p95 = percentile(p95_latencies, 0.95)
    agg_throughput = sum(throughputs) / len(throughputs)
    agg_lag = max(lags)
    agg_drain = sum(drain_times) / len(drain_times)
    total_cpu = sum(cpu_secs)
    cpu_per_million = (total_cpu / total_events * 1_000_000.0) if total_events > 0 else 0.0

    return ReplayBenchmarkResultV1(
        schema_version="replay-benchmark-v1",
        implementation=implementation,
        git_sha=git_sha,
        champion_sha256=package_sha256,
        contract_sha256=contract_sha256,
        source_dataset_sha256=source_dataset_sha256,
        workload_sha256=workload_sha256,
        repetitions=len(samples),
        source_events=total_events,
        valid_windows=total_windows,
        feature_digest=feature_digest,
        score_digest=score_digest,
        alert_digest=alert_digest,
        duplicate_rows=total_dupes,
        quarantine_rows=total_quarantines,
        p50_latency_ms=agg_p50,
        p95_latency_ms=agg_p95,
        throughput_events_per_second=round(agg_throughput, 2),
        max_consumer_lag=round(agg_lag, 2),
        lag_drain_seconds=round(agg_drain, 3),
        cpu_seconds_per_million_events=round(cpu_per_million, 2),
        peak_rss_bytes=peak_rss,
        restart_recovery_passed=all_recovery_passed,
    )


def generate_baseline_benchmark(
    *,
    git_sha: str | None = None,
    champion_sha256: str = "1" * 64,
    contract_sha256: str = "2" * 64,
    source_dataset_sha256: str = "3" * 64,
    workload_sha256: str = "4" * 64,
    repetitions: int = 5,
    source_events: int = 18720,
    valid_windows: int = 624,
    feature_digest: str = "d" * 64,
    score_digest: str = "e" * 64,
    alert_digest: str = "f" * 64,
    duplicate_rows: int = 0,
    quarantine_rows: int = 0,
    latency_samples_ms: Sequence[float] | None = None,
    p50_latency_ms: float = 4.2,
    p95_latency_ms: float = 12.8,
    throughput_events_per_second: float = 12500.0,
    max_consumer_lag: float = 120.0,
    lag_drain_seconds: float = 0.85,
    cpu_seconds_per_million_events: float = 18.5,
    peak_rss_bytes: int = 85000000,
    restart_recovery_passed: bool = True,
) -> ReplayBenchmarkResultV1:
    resolved_sha = resolve_git_sha(git_sha)

    if latency_samples_ms is not None and len(latency_samples_ms) > 0:
        p50, p95 = compute_latency_percentiles(latency_samples_ms)
        p50_latency_ms = p50
        p95_latency_ms = p95

    return ReplayBenchmarkResultV1(
        schema_version="replay-benchmark-v1",
        implementation="python-worker",
        git_sha=resolved_sha,
        champion_sha256=champion_sha256,
        contract_sha256=contract_sha256,
        source_dataset_sha256=source_dataset_sha256,
        workload_sha256=workload_sha256,
        repetitions=repetitions,
        source_events=source_events,
        valid_windows=valid_windows,
        feature_digest=feature_digest,
        score_digest=score_digest,
        alert_digest=alert_digest,
        duplicate_rows=duplicate_rows,
        quarantine_rows=quarantine_rows,
        p50_latency_ms=p50_latency_ms,
        p95_latency_ms=p95_latency_ms,
        throughput_events_per_second=throughput_events_per_second,
        max_consumer_lag=max_consumer_lag,
        lag_drain_seconds=lag_drain_seconds,
        cpu_seconds_per_million_events=cpu_seconds_per_million_events,
        peak_rss_bytes=peak_rss_bytes,
        restart_recovery_passed=restart_recovery_passed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay Streaming Worker Benchmark")
    parser.add_argument("--implementation", type=str, default="python-worker")
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--package-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--git-sha", type=str, required=True)
    parser.add_argument(
        "--api-url",
        default=os.environ.get("REPLAY_API_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--prometheus-url",
        default=os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090"),
    )
    args = parser.parse_args(argv)

    try:
        config = build_benchmark_config(
            workload_path=args.workload,
            git_sha=args.git_sha,
            package_manifest=args.package_manifest,
            api_url=args.api_url,
            prometheus_url=args.prometheus_url,
            output_dir=args.output_dir,
        )
        result = run_benchmark(config, implementation=args.implementation)
        output = write_runtime_result(result, config.output_dir)
    except Exception as exc:
        print(f"Replay benchmark unavailable: {exc}", file=sys.stderr)
        return 1

    print(f"Benchmark result written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
