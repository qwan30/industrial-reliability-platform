from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.slow
def test_published_phase1b_artifacts_are_aggregate_and_separate() -> None:
    phase1_metrics_path = Path("docs/results/phase-1-metrics.json")
    phase1b_metrics_path = Path("docs/results/phase-1b-metrics.json")

    if not phase1b_metrics_path.exists():
        pytest.skip("Phase 1B metrics not yet published")

    phase1 = json.loads(phase1_metrics_path.read_text(encoding="utf-8"))
    phase1b = json.loads(phase1b_metrics_path.read_text(encoding="utf-8"))

    assert phase1["selected_model"] is None
    assert phase1b["schema_version"] == "phase1b-benchmark-v1"
    assert "scores" not in phase1b
    assert "model_weights" not in phase1b
    assert phase1b["verdict"] in {"FEASIBLE", "NOT FEASIBLE"}
