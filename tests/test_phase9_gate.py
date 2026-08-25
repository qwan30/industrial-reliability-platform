from __future__ import annotations

import json
from pathlib import Path

from industrial_reliability.phase9_gate import (
    Phase9CertificationGate,
    _compute_self_hash,
    main,
    run_phase9_gate,
)


def test_phase9_gate_all_checks_pass() -> None:
    gate = Phase9CertificationGate()
    ok = gate.run_all_checks()
    assert ok is True
    report = gate.generate_report()
    assert report["verdict"] == "PASS"
    assert report["passed_checks"] == report["total_checks"]
    assert report["failed_checks"] == 0
    assert len(report["report_sha256"]) == 64

    # Verify self-hash integrity
    computed_hash = _compute_self_hash(report)
    assert report["report_sha256"] == computed_hash


def test_run_phase9_gate_generates_json_and_md(tmp_path: Path) -> None:
    report = run_phase9_gate(output_dir=tmp_path)
    assert report["verdict"] == "PASS"

    json_file = tmp_path / "phase-9-grounded-rca.json"
    md_file = tmp_path / "phase-9-grounded-rca.md"

    assert json_file.is_file()
    assert md_file.is_file()

    saved_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert saved_data["report_sha256"] == report["report_sha256"]
    assert "Grounded Root-Cause Analysis" in md_file.read_text(encoding="utf-8")


def test_phase9_gate_main_cli(tmp_path: Path) -> None:
    code = main(["--output-dir", str(tmp_path)])
    assert code == 0
