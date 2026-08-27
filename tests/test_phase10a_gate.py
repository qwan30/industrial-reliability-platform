from __future__ import annotations

import json
from pathlib import Path

from industrial_reliability.phase10a_gate import (
    decide_phase10a,
    main,
    run_phase10a_gate,
)
from industrial_reliability.replay_benchmark import generate_baseline_benchmark


def test_infeasible_platform_is_na_without_candidate() -> None:
    decision = decide_phase10a(
        feasible=False,
        champion=None,
        baseline=None,
    )
    assert decision.status == "N/A"
    assert decision.reason_codes == ("PLATFORM_PATH_STOPPED",)
    assert decision.baseline is None
    assert decision.candidate is None


def test_capacity_pass_avoids_spark() -> None:
    bench = generate_baseline_benchmark(
        git_sha="0" * 40,
        champion_sha256="1" * 64,
        contract_sha256="2" * 64,
        source_dataset_sha256="3" * 64,
        workload_sha256="4" * 64,
        p95_latency_ms=900.0,
        lag_drain_seconds=20.0,
        restart_recovery_passed=True,
    )
    decision = decide_phase10a(
        feasible=True,
        champion={"model_id": "statistical"},
        baseline=bench,
    )
    assert decision.status == "NOT_ADOPTED"
    assert decision.reason_codes == ("BASELINE_MEETS_CAPACITY",)


def test_run_phase10a_gate_with_infeasible_result(tmp_path: Path) -> None:
    metrics_file = tmp_path / "phase-1b-metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "schema_version": "phase1b-benchmark-v1",
                "verdict": "NOT FEASIBLE",
                "selected_model": None,
                "contract_sha256": "0" * 64,
                "source_dataset_sha256": "1" * 64,
            }
        ),
        encoding="utf-8",
    )

    decision = run_phase10a_gate(
        phase1b_result_path=metrics_file,
        output_dir=tmp_path,
    )
    assert decision.status == "N/A"
    assert (tmp_path / "phase-10a-spark-decision.json").is_file()
    assert (tmp_path / "phase-10a-spark-decision.md").is_file()
    md_content = (tmp_path / "phase-10a-spark-decision.md").read_text(encoding="utf-8")
    assert "Platform path stopped" in md_content
    assert "satisfies streaming SLA" not in md_content


def test_phase10a_main_cli(tmp_path: Path) -> None:
    metrics_file = tmp_path / "phase-1b-metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "schema_version": "phase1b-benchmark-v1",
                "verdict": "NOT FEASIBLE",
                "selected_model": None,
            }
        ),
        encoding="utf-8",
    )
    code = main(["--phase1b-result", str(metrics_file), "--output-dir", str(tmp_path)])
    assert code == 0
