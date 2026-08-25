from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.write_phase7a_airflow_decision import write_decision


def test_publisher_writes_only_not_adopted_with_exact_hashes(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\nWorkflow is manual.\n", encoding="utf-8")

    phase7 = tmp_path / "phase7-gate.json"
    phase7.write_text(json.dumps({"verdict": "PASS", "reasons": []}), encoding="utf-8")

    output = tmp_path / "airflow-decision.json"
    write_decision(
        spec=spec,
        phase7_gate=phase7,
        git_sha="a" * 40,
        output=output,
    )

    body = json.loads(output.read_text(encoding="utf-8"))
    assert body["decision"] == "NOT_ADOPTED"
    assert body["approved_recurring_workflows"] == 0
    assert body["scheduled_workflows"] == 0
    assert body["promotion_mode"] == "manual"
    assert body["airflow_installed"] is False
    assert len(body["decision_sha256"]) == 64
    assert len(body["roadmap_spec_sha256"]) == 64
    assert len(body["phase7_gate_sha256"]) == 64


def test_publisher_rejects_nonpassing_phase7_gate(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n", encoding="utf-8")

    phase7 = tmp_path / "phase7-gate.json"
    phase7.write_text(
        json.dumps({"verdict": "FAIL", "reasons": ["Checksum mismatch"]}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Phase 7 gate did not pass"):
        write_decision(
            spec=spec,
            phase7_gate=phase7,
            git_sha="a" * 40,
            output=tmp_path / "decision.json",
        )


def test_publisher_rejects_invalid_git_sha(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n", encoding="utf-8")

    phase7 = tmp_path / "phase7-gate.json"
    phase7.write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Git SHA"):
        write_decision(
            spec=spec,
            phase7_gate=phase7,
            git_sha="invalid-sha",
            output=tmp_path / "decision.json",
        )
