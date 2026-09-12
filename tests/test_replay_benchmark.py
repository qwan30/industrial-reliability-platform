from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import industrial_reliability.replay_benchmark as replay_benchmark
from industrial_reliability.decision_gate import ReplayBenchmarkSampleV1
from industrial_reliability.replay_benchmark import (
    ReplayBenchmarkConfig,
    _capture_repetition,
    _RuntimeRepetition,
    aggregate_runtime_samples,
    aggregate_samples,
    build_benchmark_config,
    compute_latency_percentiles,
    compute_stream_digest,
    generate_baseline_benchmark,
    main,
)


def _runtime_config(tmp_path: Path, repetitions: int = 2) -> ReplayBenchmarkConfig:
    return ReplayBenchmarkConfig(
        workload_path=tmp_path / "workload.json",
        range_start="2020-02-25T00:00:00",
        range_end="2020-02-25T06:00:00",
        speed=1000,
        repetitions=repetitions,
        restart_repetition=2,
        git_sha="a" * 40,
        package_manifest=tmp_path / "manifest.json",
        package_sha256="b" * 64,
        contract_sha256="c" * 64,
        source_dataset_sha256="d" * 64,
        workload_sha256="e" * 64,
        api_url="http://127.0.0.1:8000",
        prometheus_url="http://127.0.0.1:9090",
        output_dir=tmp_path / "output",
    )


def test_capture_repetition_records_peak_lag_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _runtime_config(tmp_path, repetitions=1)
    metrics = iter(
        [
            {
                "lag": 0.0,
                "latency_p50": 0.001,
                "latency_p95": 0.002,
                "accepted": 0.0,
                "duplicate": 0.0,
                "quarantine": 0.0,
                "valid_windows": 0.0,
            },
            {
                "lag": 3.0,
                "latency_p50": 0.001,
                "latency_p95": 0.002,
                "accepted": 10.0,
                "duplicate": 0.0,
                "quarantine": 0.0,
                "valid_windows": 2.0,
            },
            {
                "lag": 0.0,
                "latency_p50": 0.001,
                "latency_p95": 0.002,
                "accepted": 10.0,
                "duplicate": 0.0,
                "quarantine": 0.0,
                "valid_windows": 2.0,
            },
        ]
    )
    monkeypatch.setattr(
        replay_benchmark,
        "_prometheus_snapshot",
        lambda *_args, **_kwargs: next(metrics),
    )
    monkeypatch.setattr(
        replay_benchmark,
        "_docker_stats_sample",
        lambda: {
            "observed_at": "2020-02-25T00:00:00",
            "cpu_percent": 10.0,
            "memory_bytes": 100,
        },
    )

    def fake_request(
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, object] | None = None,
        timeout_seconds: float = 10.0,
    ) -> dict[str, object]:
        del payload, timeout_seconds
        if method == "POST":
            return {"success": True, "data": {"replay_session_id": "session-1"}}
        if url.endswith("/alerts"):
            return {"success": True, "data": {"alerts": []}}
        return {
            "success": True,
            "data": {
                "state": "COMPLETED",
                "last_sequence": 10,
                "source_dataset_sha256": config.source_dataset_sha256,
                "contract_sha256": config.contract_sha256,
            },
        }

    monkeypatch.setattr(replay_benchmark, "_request_json", fake_request)

    repetition = _capture_repetition(config, 1)

    assert repetition.sample.max_consumer_lag == 3.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repetition", 0),
        ("source_events", -1),
        ("valid_windows", -1),
        ("duplicate_rows", -1),
        ("quarantine_rows", -1),
        ("peak_rss_bytes", -1),
    ],
)
def test_replay_sample_rejects_invalid_integer_metrics(field: str, value: int) -> None:
    sample_values: dict[str, object] = {
        "repetition": 1,
        "source_events": 1,
        "valid_windows": 1,
        "p50_latency_ms": 1.0,
        "p95_latency_ms": 1.0,
        "throughput_events_per_second": 1.0,
        "max_consumer_lag": 0.0,
        "lag_drain_seconds": 0.0,
        "duplicate_rows": 0,
        "quarantine_rows": 0,
        "cpu_seconds": 0.0,
        "peak_rss_bytes": 1,
        "recovery_passed": True,
    }
    sample_values[field] = value

    with pytest.raises(ValueError, match=field):
        ReplayBenchmarkSampleV1(**sample_values)


def test_benchmark_config_rejects_non_frozen_workload(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="frozen benchmark workload"):
        build_benchmark_config(
            workload_path=tmp_path / "workload.json",
            git_sha="a" * 40,
            package_manifest=tmp_path / "manifest.json",
            api_url="http://127.0.0.1:8000",
            prometheus_url="http://127.0.0.1:9090",
            output_dir=tmp_path / "output",
        )


def test_benchmark_rejects_uncommitted_frozen_workload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_workload = (
        Path(replay_benchmark.__file__).resolve().parents[2]
        / "ops"
        / "benchmarks"
        / "replay-workload.json"
    )
    monkeypatch.setattr(
        replay_benchmark,
        "_committed_workload_bytes",
        lambda _git_sha: b"different workload bytes",
    )

    with pytest.raises(ValueError, match="does not match supplied git SHA"):
        replay_benchmark._verify_frozen_workload(expected_workload, "a" * 40)


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
        feature_digest="f" * 64,
        score_digest="0" * 64,
        alert_digest="1" * 64,
    )
    assert result.source_events == 2000
    assert result.valid_windows == 80
    assert result.p50_latency_ms == 105.0
    assert result.p95_latency_ms == 159.0
    assert result.peak_rss_bytes == 82_000_000
    assert result.restart_recovery_passed is True


def test_runtime_aggregate_retains_raw_observations_and_hashes(tmp_path: Path) -> None:
    config = _runtime_config(tmp_path)
    samples = (
        ReplayBenchmarkSampleV1(
            repetition=1,
            source_events=1000,
            valid_windows=40,
            p50_latency_ms=10.0,
            p95_latency_ms=20.0,
            throughput_events_per_second=200.0,
            max_consumer_lag=4.0,
            lag_drain_seconds=0.5,
            duplicate_rows=1,
            quarantine_rows=2,
            cpu_seconds=3.0,
            peak_rss_bytes=10_000,
            recovery_passed=True,
            timing_samples=({"elapsed_seconds": 5.0},),
            prometheus_samples=({"accepted": 1000.0},),
            container_samples=({"memory_bytes": 10_000},),
        ),
        ReplayBenchmarkSampleV1(
            repetition=2,
            source_events=1200,
            valid_windows=48,
            p50_latency_ms=12.0,
            p95_latency_ms=24.0,
            throughput_events_per_second=240.0,
            max_consumer_lag=6.0,
            lag_drain_seconds=0.7,
            duplicate_rows=0,
            quarantine_rows=1,
            cpu_seconds=3.5,
            peak_rss_bytes=12_000,
            recovery_passed=True,
            timing_samples=({"elapsed_seconds": 5.0},),
            prometheus_samples=({"accepted": 1200.0},),
            container_samples=({"memory_bytes": 12_000},),
        ),
    )
    result = aggregate_runtime_samples(
        config,
        (
            _RuntimeRepetition(samples[0], "1" * 64, "2" * 64, "3" * 64),
            _RuntimeRepetition(samples[1], "4" * 64, "5" * 64, "6" * 64),
        ),
    )

    assert result.schema_version == "replay-benchmark-v2"
    assert result.evidence_level == "RUNTIME"
    assert result.raw_samples == samples
    assert result.source_events == 2200
    assert result.restart_recovery_passed is True
    assert result.regression_budget is None
    assert result.limitations == ("baseline only; no budget established",)
    assert result.self_sha256
    assert result.with_computed_hash().self_sha256 == result.self_sha256


def test_benchmark_cli_fails_without_runtime_observations(tmp_path: Path) -> None:
    workload = tmp_path / "workload.json"
    workload.write_text(
        json.dumps(
            {
                "schema_version": "replay-workload-v1",
                "range_start": "2020-02-25T00:00:00",
                "range_end": "2020-02-25T06:00:00",
                "speed": 1000,
                "repetitions": 1,
                "restart_repetition": 1,
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "champion-package-v2",
                "model_version": "champion-statistical-v1",
                "contract_sha256": "c" * 64,
                "source_dataset_sha256": "d" * 64,
                "artifact_sha256": {"artifact.bin": hashlib.sha256(b"artifact").hexdigest()},
            }
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "--workload",
            str(workload),
            "--package-manifest",
            str(manifest),
            "--output-dir",
            str(tmp_path / "output"),
            "--git-sha",
            "b" * 40,
        ]
    )

    assert code == 1
    assert not (tmp_path / "output" / "benchmark.json").exists()
