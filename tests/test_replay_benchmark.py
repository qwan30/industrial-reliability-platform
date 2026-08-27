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


def test_replay_benchmark_cli(tmp_path: Path) -> None:
    code = main(["--output", str(tmp_path), "--git-sha", "b" * 40])
    assert code == 0
    assert (tmp_path / "benchmark.json").is_file()
