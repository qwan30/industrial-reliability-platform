import asyncio
import json
from pathlib import Path

import pytest

from industrial_reliability.fault_report import (
    DrillMetricDeltasV1,
    DrillResultV1,
    classify_drill,
    execute_in_process_drills,
    publish_drill_report,
)


def test_classify_service_outage() -> None:
    deltas = DrillMetricDeltasV1(
        score_unavailable_delta=5.0,
        score_ok_delta=0.0,
        telemetry_quarantined_delta=0.0,
        anomaly_decisions_delta=0.0,
        alert_events_delta=0.0,
    )
    classification, reason = classify_drill(deltas)
    assert classification == "SERVICE"
    assert "scoring unavailable" in reason.lower()


def test_classify_data_fault() -> None:
    deltas = DrillMetricDeltasV1(
        telemetry_quarantined_delta=3.0,
        score_unavailable_delta=0.0,
        anomaly_decisions_delta=0.0,
        alert_events_delta=0.0,
    )
    classification, reason = classify_drill(deltas)
    assert classification == "DATA"
    assert "quarantined" in reason.lower()


def test_classify_machine_abnormal() -> None:
    deltas = DrillMetricDeltasV1(
        score_ok_delta=10.0,
        anomaly_decisions_delta=8.0,
        alert_events_delta=1.0,
        telemetry_quarantined_delta=0.0,
        score_unavailable_delta=0.0,
    )
    classification, reason = classify_drill(deltas)
    assert classification == "MACHINE"
    assert "anomalous" in reason.lower()


def test_publish_and_verify_fault_report(tmp_path: Path) -> None:
    drills = [
        DrillResultV1(
            drill_type="scoring-outage",
            expected_classification="SERVICE",
            actual_classification="SERVICE",
            passed=True,
            deltas=DrillMetricDeltasV1(score_unavailable_delta=5.0),
            evidence_summary="5 scoring requests timed out, 0 quarantine, 0 anomalies",
        ),
        DrillResultV1(
            drill_type="malformed-telemetry",
            expected_classification="DATA",
            actual_classification="DATA",
            passed=True,
            deltas=DrillMetricDeltasV1(telemetry_quarantined_delta=10.0),
            evidence_summary="10 malformed records quarantined, 0 downstream contamination",
        ),
        DrillResultV1(
            drill_type="known-abnormal-replay",
            expected_classification="MACHINE",
            actual_classification="MACHINE",
            passed=True,
            deltas=DrillMetricDeltasV1(
                score_ok_delta=20.0, anomaly_decisions_delta=12.0, alert_events_delta=1.0
            ),
            evidence_summary="Scorer detected 12 anomalous windows, alert opened",
        ),
    ]

    json_path = tmp_path / "fault-report.json"
    md_path = tmp_path / "fault-report.md"

    report = publish_drill_report(
        drills,
        json_path=json_path,
        md_path=md_path,
        git_sha="a" * 40,
    )
    assert report.all_passed is True
    assert report.evidence_level == "UNIT"
    assert report.git_sha == "a" * 40
    assert json_path.is_file()
    assert md_path.is_file()

    # Verify JSON self-hash
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "phase8-fault-report-v1"
    assert data["evidence_level"] == "UNIT"
    assert data["git_sha"] == "a" * 40
    assert len(data["self_sha256"]) == 64

    # Verify Markdown
    md_text = md_path.read_text(encoding="utf-8")
    assert "# Phase 8 Observability & Reliability Drill Report" in md_text
    assert "scoring-outage" in md_text
    assert "malformed-telemetry" in md_text
    assert "known-abnormal-replay" in md_text


def test_fault_report_is_unit_evidence(tmp_path: Path) -> None:
    drills = asyncio.run(execute_in_process_drills())
    assert all(result.passed for result in drills)
    published = publish_drill_report(
        drills,
        json_path=tmp_path / "report.json",
        md_path=tmp_path / "report.md",
        git_sha="a" * 40,
    )
    assert published.evidence_level == "UNIT"
    assert published.git_sha == "a" * 40


@pytest.mark.parametrize("invalid_sha", ["0" * 40, "abc", "G" * 40, ""])
def test_publish_drill_report_rejects_invalid_git_sha(tmp_path: Path, invalid_sha: str) -> None:
    with pytest.raises(ValueError, match="git_sha"):
        publish_drill_report(
            [],
            json_path=tmp_path / "report.json",
            md_path=tmp_path / "report.md",
            git_sha=invalid_sha,
        )


@pytest.mark.asyncio
async def test_execute_in_process_drills() -> None:
    from industrial_reliability.fault_report import execute_in_process_drills

    results = await execute_in_process_drills()
    assert len(results) == 3
    assert all(r.passed for r in results)


def test_fault_report_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from industrial_reliability.fault_report import main

    json_out = tmp_path / "drills.json"
    md_out = tmp_path / "drills.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "fault_report.py",
            "--json-output",
            str(json_out),
            "--md-output",
            str(md_out),
        ],
    )
    main()
    assert json_out.is_file()
    assert md_out.is_file()
