"""Unit tests for Phase 8 live fault isolation gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from industrial_reliability.fault_report import DrillMetricDeltasV1
from industrial_reliability.phase8_live_gate import (
    LiveDrillResultV1,
    execute_live_drills,
    main,
    publish_live_drill_report,
)


def test_publish_live_drill_report(tmp_path: Path) -> None:
    drills = [
        LiveDrillResultV1(
            drill_type="scoring-outage",
            expected_classification="SERVICE",
            actual_classification="SERVICE",
            passed=True,
            deltas=DrillMetricDeltasV1(score_unavailable_delta=1.0),
            evidence_summary="Scoring unavailable delta",
        ),
        LiveDrillResultV1(
            drill_type="malformed-telemetry",
            expected_classification="DATA",
            actual_classification="DATA",
            passed=True,
            deltas=DrillMetricDeltasV1(telemetry_quarantined_delta=1.0),
            evidence_summary="Telemetry quarantined delta",
        ),
        LiveDrillResultV1(
            drill_type="known-abnormal-replay",
            expected_classification="MACHINE",
            actual_classification="MACHINE",
            passed=True,
            deltas=DrillMetricDeltasV1(anomaly_decisions_delta=1.0),
            evidence_summary="Anomaly decisions delta",
        ),
    ]

    json_path = tmp_path / "report.json"
    md_path = tmp_path / "report.md"
    git_sha = "a" * 40

    report = publish_live_drill_report(
        drills,
        json_path=json_path,
        md_path=md_path,
        git_sha=git_sha,
    )

    assert report.all_passed is True
    assert report.evidence_level == "LIVE"
    assert report.git_sha == git_sha
    assert report.schema_version == "phase8-live-fault-drills-v1"
    assert len(report.self_sha256) == 64

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "phase8-live-fault-drills-v1"
    assert data["evidence_level"] == "LIVE"
    assert data["git_sha"] == git_sha
    assert data["self_sha256"] == report.self_sha256

    md_text = md_path.read_text(encoding="utf-8")
    assert "Live Evidence" in md_text
    assert git_sha in md_text


@pytest.mark.parametrize("invalid_sha", ["0" * 40, "abc", "G" * 40, ""])
def test_publish_live_drill_report_rejects_invalid_git_sha(tmp_path: Path, invalid_sha: str) -> None:
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


def test_phase8_live_gate_cli(tmp_path: Path) -> None:
    out_dir = tmp_path / "live_out"
    code = main(["--output-dir", str(out_dir), "--git-sha", "b" * 40])
    assert code == 0
    assert (out_dir / "phase-8-live-fault-drills.json").exists()
    assert (out_dir / "phase-8-live-fault-drills.md").exists()
