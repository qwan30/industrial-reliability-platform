"""Unit tests for the Phase 8 fault-isolation certification gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import industrial_reliability.phase8_live_gate as phase8_live_gate
from industrial_reliability.fault_report import DrillMetricDeltasV1, DrillResultV1
from industrial_reliability.phase8_live_gate import (
    PHASE8_REPORT_BASENAME,
    LiveFaultReportV1,
    execute_live_drills,
    main,
    publish_live_drill_report,
    run_phase8_live_gate,
)


def test_publish_live_drill_report(tmp_path: Path) -> None:
    drills = [
        DrillResultV1(
            drill_type="scoring-outage",
            expected_classification="SERVICE",
            actual_classification="SERVICE",
            passed=True,
            deltas=DrillMetricDeltasV1(score_unavailable_delta=1.0),
            evidence_summary="Scoring unavailable delta",
        ),
        DrillResultV1(
            drill_type="malformed-telemetry",
            expected_classification="DATA",
            actual_classification="DATA",
            passed=True,
            deltas=DrillMetricDeltasV1(telemetry_quarantined_delta=1.0),
            evidence_summary="Telemetry quarantined delta",
        ),
        DrillResultV1(
            drill_type="known-abnormal-replay",
            expected_classification="MACHINE",
            actual_classification="MACHINE",
            passed=True,
            deltas=DrillMetricDeltasV1(anomaly_decisions_delta=1.0),
            evidence_summary="Anomaly decisions delta",
        ),
    ]

    json_path = tmp_path / f"{PHASE8_REPORT_BASENAME}.json"
    md_path = tmp_path / f"{PHASE8_REPORT_BASENAME}.md"
    git_sha = "a" * 40

    report = publish_live_drill_report(
        drills,
        json_path=json_path,
        md_path=md_path,
        git_sha=git_sha,
    )

    assert report.all_passed is True
    assert report.evidence_level == "UNIT"
    assert report.verdict == "PASS"
    assert report.git_sha == git_sha
    assert report.schema_version == "phase8-fault-report-v1"
    assert len(report.self_sha256) == 64
    assert report.simulated_components

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "phase8-fault-report-v1"
    assert data["evidence_level"] == "UNIT"
    assert data["verdict"] == "PASS"
    assert data["git_sha"] == git_sha
    assert data["self_sha256"] == report.self_sha256
    assert data["simulated_components"]

    md_text = md_path.read_text(encoding="utf-8")
    assert "Fault Drill Report" in md_text
    assert git_sha in md_text
    assert "Simulated Components" in md_text


def test_publish_live_drill_report_rejects_evidence_relabeling(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        publish_live_drill_report(
            [],
            json_path=tmp_path / "report.json",
            md_path=tmp_path / "report.md",
            git_sha="a" * 40,
            evidence_level="LIVE",
        )


@pytest.mark.parametrize("invalid_sha", ["0" * 40, "abc", "G" * 40, ""])
def test_publish_live_drill_report_rejects_invalid_git_sha(
    tmp_path: Path, invalid_sha: str
) -> None:
    with pytest.raises(ValueError, match="git_sha"):
        publish_live_drill_report(
            [],
            json_path=tmp_path / "report.json",
            md_path=tmp_path / "report.md",
            git_sha=invalid_sha,
        )


@pytest.mark.asyncio
async def test_execute_live_drills() -> None:
    results = await execute_live_drills()
    assert len(results) == 3
    assert all(r.passed for r in results)
    assert results[0].actual_classification == "SERVICE"
    assert results[1].actual_classification == "DATA"
    assert results[2].actual_classification == "MACHINE"


def test_phase8_live_gate_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "industrial_reliability.phase8_live_gate._runtime_preflight",
        lambda: (("runtime prerequisites unavailable",), ()),
    )
    out_dir = tmp_path / "live_out"
    code = main(["--output-dir", str(out_dir), "--git-sha", "b" * 40])
    assert code == 1
    assert (out_dir / "phase-8-live-fault-drills.json").exists()
    assert (out_dir / "phase-8-live-fault-drills.md").exists()


def test_request_status_accepts_plaintext_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    class PlaintextResponse:
        status = 200

        def __enter__(self) -> PlaintextResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        phase8_live_gate,
        "urlopen",
        lambda *_args, **_kwargs: PlaintextResponse(),
    )

    phase8_live_gate._request_status("GET", "http://127.0.0.1:9090/-/ready")


def test_phase8_runtime_runner_is_blocked_without_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "industrial_reliability.phase8_live_gate._runtime_preflight",
        lambda: (("runtime prerequisites unavailable",), ()),
    )
    report = run_phase8_live_gate(output_dir=tmp_path, git_sha="a" * 40)

    assert isinstance(report, LiveFaultReportV1)
    assert report.evidence_level == "INTEGRATION"
    assert report.verdict == "BLOCKED"
    assert report.all_passed is False
    assert report.drills == ()


def test_broker_interruption_waits_for_active_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter(({"state": "CREATED"}, {"state": "RUNNING"}))
    monkeypatch.setattr(
        phase8_live_gate,
        "_replay_status",
        lambda _api_url, _session_id: next(states),
    )
    monkeypatch.setattr(phase8_live_gate.time, "sleep", lambda _seconds: None)

    phase8_live_gate._wait_for_replay_active("http://127.0.0.1:8000", "session-1")


def test_malformed_telemetry_requires_worker_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = {
        "accepted": 1,
        "duplicate": 0,
        "quarantine": 0,
        "score_ok": 1,
        "score_unavailable": 0,
        "anomaly": 1,
        "alerts": 1,
    }
    after = {**before, "quarantine": 1}
    counters = iter((before, after))
    monkeypatch.setattr(phase8_live_gate, "_runtime_counters", lambda _url: next(counters))

    async def publish_malformed() -> bool:
        return True

    monkeypatch.setattr(phase8_live_gate, "_publish_malformed_telemetry", publish_malformed)
    monkeypatch.setattr(
        phase8_live_gate,
        "_compose_service_healthy",
        lambda _service: False,
    )
    monkeypatch.setattr(phase8_live_gate.time, "sleep", lambda _seconds: None)

    result = phase8_live_gate._run_malformed_telemetry(
        "http://127.0.0.1:8000",
        "http://127.0.0.1:9090",
    )

    assert result.passed is False
