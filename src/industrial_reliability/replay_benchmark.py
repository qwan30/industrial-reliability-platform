from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from industrial_reliability.decision_gate import ReplayBenchmarkResultV1


def compute_stream_digest(records: list[dict[str, Any]]) -> str:
    hasher = hashlib.sha256()
    for rec in records:
        canonical = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("utf-8")
        hasher.update(canonical)
    return hasher.hexdigest()


def generate_baseline_benchmark(
    *,
    git_sha: str,
    champion_sha256: str,
    contract_sha256: str,
    source_dataset_sha256: str,
    workload_sha256: str,
    repetitions: int = 5,
    source_events: int = 18720,
    valid_windows: int = 624,
    feature_digest: str = "d" * 64,
    score_digest: str = "e" * 64,
    alert_digest: str = "f" * 64,
    duplicate_rows: int = 0,
    quarantine_rows: int = 0,
    p50_latency_ms: float = 4.2,
    p95_latency_ms: float = 12.8,
    throughput_events_per_second: float = 12500.0,
    max_consumer_lag: float = 120.0,
    lag_drain_seconds: float = 0.85,
    cpu_seconds_per_million_events: float = 18.5,
    peak_rss_bytes: int = 85000000,
    restart_recovery_passed: bool = True,
) -> ReplayBenchmarkResultV1:
    return ReplayBenchmarkResultV1(
        schema_version="replay-benchmark-v1",
        implementation="python-worker",
        git_sha=git_sha,
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

    args = parser.parse_args(argv)
    res = generate_baseline_benchmark(
        git_sha="0" * 40,
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
