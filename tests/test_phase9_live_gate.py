"""Unit tests for Phase 9 dual-mode RCA certification gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from industrial_reliability.phase9_live_gate import (
    Phase9LiveGate,
    main,
)
from industrial_reliability.report_hashes import compute_self_hash


def test_phase9_live_gate_fallback_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RCA_OPENAI_API_KEY", raising=False)
    gate = Phase9LiveGate()
    assert gate.provider_mode == "FALLBACK_ONLY"

    passed = gate.run_all_checks()
    assert passed is True
    assert len(gate.checks) == 4

    git_sha = "c" * 40
    report = gate.generate_report(git_sha=git_sha, evidence_level="LIVE")
    assert report["schema_version"] == "phase-9-rca-fallback-v1"
    assert report["evidence_level"] == "LIVE"
    assert report["provider_mode"] == "FALLBACK_ONLY"
    assert report["verdict"] == "PASS"
    assert report["git_sha"] == git_sha
    assert len(report["report_sha256"]) == 64
    assert report["simulated_components"]
    assert compute_self_hash(report, "report_sha256") == report["report_sha256"]


def test_phase9_live_gate_live_openai_mode(tmp_path: Path) -> None:
    gate = Phase9LiveGate(api_key="sk-test-key-mock", model="gpt-4o-mini")
    assert gate.provider_mode == "LIVE_OPENAI"

    passed = gate.run_all_checks()
    assert passed is True
    assert len(gate.checks) == 5

    git_sha = "d" * 40
    report = gate.generate_report(git_sha=git_sha, evidence_level="LIVE")
    assert report["schema_version"] == "phase-9-rca-openai-v1"
    assert report["evidence_level"] == "LIVE"
    assert report["provider_mode"] == "LIVE_OPENAI"
    assert report["verdict"] == "PASS"
    assert report["git_sha"] == git_sha
    assert len(report["report_sha256"]) == 64
    assert report["simulated_components"]


@pytest.mark.parametrize("invalid_sha", ["0" * 40, "abc", "G" * 40, ""])
def test_phase9_live_gate_rejects_invalid_git_sha(invalid_sha: str) -> None:
    gate = Phase9LiveGate()
    gate.run_all_checks()
    with pytest.raises(ValueError, match="git_sha"):
        gate.generate_report(git_sha=invalid_sha)


def test_phase9_live_gate_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RCA_OPENAI_API_KEY", raising=False)
    out_dir = tmp_path / "live_out"
    code = main(["--output-dir", str(out_dir), "--git-sha", "e" * 40])
    assert code == 0
    assert (out_dir / "phase-9-rca-fallback.json").exists()
    assert (out_dir / "phase-9-rca-fallback.md").exists()


def test_phase9_live_gate_cli_openai_suffix(tmp_path: Path) -> None:
    gate = Phase9LiveGate(api_key="sk-test-key-mock", model="gpt-4o-mini")
    assert gate.provider_mode == "LIVE_OPENAI"
    gate.run_all_checks()
    report = gate.generate_report(git_sha="f" * 40, evidence_level="LIVE")
    assert report["schema_version"] == "phase-9-rca-openai-v1"
    assert report["evidence_level"] == "LIVE"
