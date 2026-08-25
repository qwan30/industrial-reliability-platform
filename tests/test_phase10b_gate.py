from __future__ import annotations

import json
from pathlib import Path

import pytest

from industrial_reliability.phase10b_gate import (
    decide_phase10b_applicability,
    main,
    run_phase10b_gate,
)


@pytest.mark.parametrize("model_id", ["statistical", "isolation_forest"])
def test_classical_champion_is_na_without_candidate(model_id: str) -> None:
    decision = decide_phase10b_applicability(
        feasible=True,
        champion={"model_id": model_id, "manifest_sha256": "a" * 64},
    )
    assert decision.status == "N/A"
    assert decision.reason_codes == ("NON_PYTORCH_CHAMPION",)
    assert decision.candidate is None


def test_infeasible_platform_is_na() -> None:
    decision = decide_phase10b_applicability(
        feasible=False,
        champion=None,
    )
    assert decision.status == "N/A"
    assert decision.reason_codes == ("PLATFORM_PATH_STOPPED",)


def test_autoencoder_champion_decision() -> None:
    decision = decide_phase10b_applicability(
        feasible=True,
        champion={"model_id": "autoencoder", "manifest_sha256": "b" * 64},
    )
    assert decision.status == "NOT_ADOPTED"
    assert decision.reason_codes == ("BASELINE_MEETS_LATENCY_BUDGET",)


def test_run_phase10b_gate(tmp_path: Path) -> None:
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
    decision = run_phase10b_gate(
        phase1b_result_path=metrics_file,
        output_dir=tmp_path,
    )
    assert decision.status == "N/A"
    assert (tmp_path / "phase-10b-openvino-decision.json").is_file()
    assert (tmp_path / "phase-10b-openvino-decision.md").is_file()


def test_phase10b_main_cli(tmp_path: Path) -> None:
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
