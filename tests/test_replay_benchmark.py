from __future__ import annotations

from pathlib import Path

from industrial_reliability.replay_benchmark import (
    compute_latency_percentiles,
    compute_stream_digest,
    generate_baseline_benchmark,
    main,
)


def test_compute_stream_digest_is_deterministic() -> None:
    records = [
        {"seq": 1, "val": 10.5},
        {"seq": 2, "val": 12.0},
    ]
    digest1 = compute_stream_digest(records)
    digest2 = compute_stream_digest(records)
    assert digest1 == digest2
    assert len(digest1) == 64


def test_compute_latency_percentiles() -> None:
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    p50, p95 = compute_latency_percentiles(samples)
    assert p50 == 5.5
    assert p95 == 9.55

    assert compute_latency_percentiles([]) == (0.0, 0.0)


def test_generate_baseline_benchmark_with_samples() -> None:
    samples = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
    bench = generate_baseline_benchmark(
        git_sha="a" * 40,
        champion_sha256="1" * 64,
        contract_sha256="2" * 64,
        source_dataset_sha256="3" * 64,
        workload_sha256="4" * 64,
        latency_samples_ms=samples,
    )
    assert bench.implementation == "python-worker"
    assert bench.p50_latency_ms == 11.0
    assert bench.p95_latency_ms == 19.1
    assert bench.git_sha == "a" * 40
    assert bench.restart_recovery_passed is True


def test_aggregate_samples_is_recomputable() -> None:
    from industrial_reliability.decision_gate import ReplayBenchmarkSampleV1
    from industrial_reliability.replay_benchmark import aggregate_samples

    samples = (
        ReplayBenchmarkSampleV1(
            repetition=1,
            source_events=1000,
            valid_windows=40,
            p50_latency_ms=100.0,
            p95_latency_ms=140.0,
            throughput_events_per_second=250.0,
            max_consumer_lag=8.0,
            lag_drain_seconds=1.2,
            duplicate_rows=0,
            quarantine_rows=0,
            cpu_seconds=3.0,
            peak_rss_bytes=80_000_000,
            recovery_passed=True,
        ),
        ReplayBenchmarkSampleV1(
            repetition=2,
            source_events=1000,
            valid_windows=40,
            p50_latency_ms=110.0,
            p95_latency_ms=160.0,
            throughput_events_per_second=245.0,
            max_consumer_lag=6.0,
            lag_drain_seconds=0.9,
            duplicate_rows=0,
            quarantine_rows=1,
            cpu_seconds=3.2,
            peak_rss_bytes=82_000_000,
            recovery_passed=True,
        ),
    )
    result = aggregate_samples(
        git_sha="a" * 40,
        package_sha256="b" * 64,
        contract_sha256="c" * 64,
        source_dataset_sha256="d" * 64,
        workload_sha256="e" * 64,
        samples=samples,
    )
    assert result.source_events == 2000
    assert result.valid_windows == 80
    assert result.p50_latency_ms == 105.0
    assert result.p95_latency_ms == 159.0
    assert result.peak_rss_bytes == 82_000_000
    assert result.restart_recovery_passed is True


def test_replay_benchmark_cli(tmp_path: Path) -> None:
    code = main(["--output", str(tmp_path), "--git-sha", "b" * 40])
    assert code == 0
    assert (tmp_path / "benchmark.json").is_file()
