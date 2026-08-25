from __future__ import annotations

import json
from pathlib import Path

import pytest

from industrial_reliability.decision_gate import (
    OptionalTechnologyDecisionV1,
    ReplayBenchmarkResultV1,
    write_decision,
)


def _make_benchmark() -> ReplayBenchmarkResultV1:
    return ReplayBenchmarkResultV1(
        schema_version="replay-benchmark-v1",
        implementation="python-worker",
        git_sha="a" * 40,
        champion_sha256="b" * 64,
        contract_sha256="c" * 64,
        source_dataset_sha256="d" * 64,
        workload_sha256="e" * 64,
        repetitions=5,
        source_events=1000,
        valid_windows=100,
        feature_digest="f" * 64,
        score_digest="1" * 64,
        alert_digest="2" * 64,
        duplicate_rows=0,
        quarantine_rows=0,
        p50_latency_ms=5.0,
        p95_latency_ms=15.0,
        throughput_events_per_second=10000.0,
        max_consumer_lag=50.0,
        lag_drain_seconds=1.0,
        cpu_seconds_per_million_events=20.0,
        peak_rss_bytes=1000000,
        restart_recovery_passed=True,
    )


def test_decision_is_canonical_and_self_hashed(tmp_path: Path) -> None:
    bench = _make_benchmark()
    decision = OptionalTechnologyDecisionV1(
        schema_version="test-decision-v1",
        technology="spark",
        status="NOT_ADOPTED",
        git_sha="a" * 40,
        champion_sha256="b" * 64,
        contract_sha256="c" * 64,
        source_dataset_sha256="d" * 64,
        reason_codes=("BASELINE_MEETS_CAPACITY",),
        baseline=bench,
        candidate=None,
        parity_passed=None,
        benefit_passed=None,
        limitations=("Test limitation",),
    )
    first = write_decision(decision, tmp_path / "first.json")
    second = write_decision(decision, tmp_path / "second.json")
    assert first.read_bytes() == second.read_bytes()
    data = json.loads(first.read_text(encoding="utf-8"))
    assert len(data["decision_sha256"]) == 64


@pytest.mark.parametrize("invalid_val", [float("nan"), float("inf"), -1.0])
def test_benchmark_rejects_invalid_latency(invalid_val: float) -> None:
    with pytest.raises(ValueError, match="p95_latency_ms"):
        ReplayBenchmarkResultV1(
            schema_version="replay-benchmark-v1",
            implementation="python-worker",
            git_sha="a" * 40,
            champion_sha256="b" * 64,
            contract_sha256="c" * 64,
            source_dataset_sha256="d" * 64,
            workload_sha256="e" * 64,
            repetitions=5,
            source_events=1000,
            valid_windows=100,
            feature_digest="f" * 64,
            score_digest="1" * 64,
            alert_digest="2" * 64,
            duplicate_rows=0,
            quarantine_rows=0,
            p50_latency_ms=5.0,
            p95_latency_ms=invalid_val,
            throughput_events_per_second=10000.0,
            max_consumer_lag=50.0,
            lag_drain_seconds=1.0,
            cpu_seconds_per_million_events=20.0,
            peak_rss_bytes=1000000,
            restart_recovery_passed=True,
        )


def test_decision_rejects_adoption_without_candidate() -> None:
    with pytest.raises(ValueError, match="ADOPTED decision requires candidate evidence"):
        OptionalTechnologyDecisionV1(
            schema_version="test-decision-v1",
            technology="spark",
            status="ADOPTED",
            git_sha="a" * 40,
            champion_sha256="b" * 64,
            contract_sha256="c" * 64,
            source_dataset_sha256="d" * 64,
            reason_codes=("ADOPTED",),
            baseline=None,
            candidate=None,
            parity_passed=True,
            benefit_passed=True,
            limitations=(),
        )
