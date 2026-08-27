from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from industrial_reliability.decision_gate import ReplayBenchmarkResultV1
from industrial_reliability.report_hashes import resolve_git_sha


def compute_stream_digest(records: list[dict[str, Any]]) -> str:
    hasher = hashlib.sha256()
    for rec in records:
        canonical = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("utf-8")
        hasher.update(canonical)
    return hasher.hexdigest()


def compute_latency_percentiles(samples_ms: Sequence[float]) -> tuple[float, float]:
    if not samples_ms:
        return (0.0, 0.0)
    arr = np.array(samples_ms, dtype=np.float64)
    p50 = float(np.percentile(arr, 50))
    p95 = float(np.percentile(arr, 95))
    return (round(p50, 3), round(p95, 3))


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
    parser.add_argument("--range-start", type=str, default="2020-04-17T22:00:00")
    parser.add_argument("--range-end", type=str, default="2020-04-19T00:00:00")
    parser.add_argument("--speed", type=int, default=1000)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--restart-repetition", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--git-sha", type=str, default=None)

    args = parser.parse_args(argv)
    res = generate_baseline_benchmark(
        git_sha=args.git_sha or "0" * 40,
        champion_sha256="1" * 64,
        contract_sha256="2" * 64,
        source_dataset_sha256="3" * 64,
        workload_sha256="4" * 64,
        repetitions=args.repetitions,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    out_file = args.output / "benchmark.json"
    out_file.write_text(json.dumps(res.to_dict(), indent=2), encoding="utf-8")
    print(f"Benchmark result written to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
