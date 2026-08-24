from __future__ import annotations

import json
from pathlib import Path

import pytest

from industrial_reliability.phase6_gate import Phase6Evidence, write_gate


def test_write_phase6_gate_validates_and_writes_file(tmp_path: Path) -> None:
    output_file = tmp_path / "phase6-gate.json"
    evidence = Phase6Evidence(
        console_feed_stream_passed=True,
        reconnectable_sse_passed=True,
        react_components_certified=True,
        e2e_real_click_flow_passed=True,
        branch_coverage_met=True,
        code_git_sha="a" * 40,
        source_dataset_sha256="b" * 64,
        contract_sha256="c" * 64,
        model_version="champion-statistical-v1",
        python_coverage_pct=87.74,
        typescript_coverage_pct=89.85,
        console_bundle_sha256="d" * 64,
    )

    write_gate(output_file, evidence)
    assert output_file.is_file()

    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert data["console_feed_stream_passed"] is True
    assert "gate_sha256" in data


def test_write_phase6_gate_rejects_missing_pass(tmp_path: Path) -> None:
    output_file = tmp_path / "phase6-gate.json"
    evidence = Phase6Evidence(
        console_feed_stream_passed=True,
        reconnectable_sse_passed=False,  # fails gate
        react_components_certified=True,
        e2e_real_click_flow_passed=True,
        branch_coverage_met=True,
        code_git_sha="a" * 40,
        source_dataset_sha256="b" * 64,
        contract_sha256="c" * 64,
        model_version="champion-statistical-v1",
        python_coverage_pct=87.74,
        typescript_coverage_pct=89.85,
        console_bundle_sha256="d" * 64,
    )

    with pytest.raises(ValueError, match="reconnectable_sse_passed is not True"):
        write_gate(output_file, evidence)
