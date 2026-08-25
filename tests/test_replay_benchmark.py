from __future__ import annotations

from pathlib import Path

from industrial_reliability.replay_benchmark import (
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


def test_generate_baseline_benchmark() -> None:
    bench = generate_baseline_benchmark(
        git_sha="0" * 40,
        champion_sha256="1" * 64,
        contract_sha256="2" * 64,
        source_dataset_sha256="3" * 64,
        workload_sha256="4" * 64,
    )
    assert bench.implementation == "python-worker"
    assert bench.p95_latency_ms == 12.8
    assert bench.restart_recovery_passed is True


def test_replay_benchmark_cli(tmp_path: Path) -> None:
    code = main(["--output", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "benchmark.json").is_file()
