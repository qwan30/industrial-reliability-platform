"""Unit tests for Phase 9 dual-mode RCA certification gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from unittest.mock import Mock

from industrial_reliability.phase9_live_gate import (
    Phase9LiveGate,
    ProviderCallReceipt,
    check_live_openai_generation,
    main,
    run_phase9_live_gate,
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
    report = gate.generate_report(git_sha=git_sha)
    assert report["schema_version"] == "phase-9-rca-fallback-v1"
    assert report["evidence_level"] == "IN_PROCESS"
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


def test_dummy_key_does_not_create_live_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "industrial_reliability.phase9_live_gate.check_live_openai_generation",
        Mock(side_effect=RuntimeError("provider not contacted")),
    )
    report = run_phase9_live_gate(
        output_dir=tmp_path,
        git_sha="a" * 40,
        api_key="dummy",
        model="test-model",
    )
    assert report["evidence_level"] == "IN_PROCESS"
    assert report["provider_mode"] == "FALLBACK_ONLY"
    assert report["dependency_receipts"] == []


def test_live_key_creates_live_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "industrial_reliability.phase9_live_gate.check_live_openai_generation",
        Mock(
            return_value=ProviderCallReceipt(
                dependency="openai",
                model="gpt-4o-mini",
                report_id="rca-mock-123",
                evidence_bundle_sha256="1" * 64,
            )
        ),
    )
    report = run_phase9_live_gate(
        output_dir=tmp_path,
        git_sha="a" * 40,
        api_key="sk-real-mock",
        model="gpt-4o-mini",
    )
    assert report["evidence_level"] == "LIVE"
    assert report["provider_mode"] == "LIVE_OPENAI"
    assert report["dependency_receipts"] == [
        {
            "dependency": "openai",
            "model": "gpt-4o-mini",
            "report_id": "rca-mock-123",
            "evidence_bundle_sha256": "1" * 64,
        }
    ]


def test_check_live_openai_generation_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_report = Mock(
        status="COMPLETE",
        provider_model="gpt-4o-mini",
        report_id="rca-live-456",
        evidence_bundle_sha256="2" * 64,
    )
    mock_generator_cls = Mock()
    mock_generator_instance = Mock()
    mock_generator_instance.generate.return_value = mock_report
    mock_generator_cls.return_value = mock_generator_instance

    monkeypatch.setattr("industrial_reliability.phase9_live_gate.OpenAiRcaGenerator", mock_generator_cls)
    monkeypatch.setattr("industrial_reliability.phase9_live_gate.OpenAI", Mock())

    receipt = check_live_openai_generation("sk-test", "gpt-4o-mini")
    assert receipt == ProviderCallReceipt(
        dependency="openai",
        model="gpt-4o-mini",
        report_id="rca-live-456",
        evidence_bundle_sha256="2" * 64,
    )


def test_check_live_openai_generation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_report = Mock(
        status="UNAVAILABLE",
        provider_model=None,
        report_id="rca-fallback-123",
        evidence_bundle_sha256="3" * 64,
    )
    mock_generator_cls = Mock()
    mock_generator_instance = Mock()
    mock_generator_instance.generate.return_value = mock_report
    mock_generator_cls.return_value = mock_generator_instance

    monkeypatch.setattr("industrial_reliability.phase9_live_gate.OpenAiRcaGenerator", mock_generator_cls)
    monkeypatch.setattr("industrial_reliability.phase9_live_gate.OpenAI", Mock())

    with pytest.raises(RuntimeError, match="provider did not return a complete grounded report"):
        check_live_openai_generation("sk-test", "gpt-4o-mini")
