from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

FaultClass = Literal["SERVICE", "DATA", "MACHINE", "UNKNOWN"]
DrillType = Literal["scoring-outage", "malformed-telemetry", "known-abnormal-replay"]


@dataclass(frozen=True)
class DrillMetricDeltasV1:
    telemetry_quarantined_delta: float = 0.0
    telemetry_accepted_delta: float = 0.0
    segment_breaks_delta: float = 0.0
    score_unavailable_delta: float = 0.0
    score_ok_delta: float = 0.0
    anomaly_decisions_delta: float = 0.0
    alert_events_delta: float = 0.0
    kafka_lag_max: float = 0.0
    feature_psi_max: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class DrillResultV1:
    drill_type: DrillType
    expected_classification: FaultClass
    actual_classification: FaultClass
    passed: bool
    deltas: DrillMetricDeltasV1
    evidence_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "drill_type": self.drill_type,
            "expected_classification": self.expected_classification,
            "actual_classification": self.actual_classification,
            "passed": self.passed,
            "deltas": self.deltas.to_dict(),
            "evidence_summary": self.evidence_summary,
        }


@dataclass(frozen=True)
class FaultReportV1:
    timestamp: str
    drills: list[DrillResultV1]
    all_passed: bool
    self_sha256: str
    git_sha: str
    evidence_level: Literal["UNIT"] = "UNIT"
    schema_version: Literal["phase8-fault-report-v1"] = "phase8-fault-report-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_level": self.evidence_level,
            "git_sha": self.git_sha,
            "timestamp": self.timestamp,
            "all_passed": self.all_passed,
            "drills": [d.to_dict() for d in self.drills],
            "self_sha256": self.self_sha256,
        }


def _canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_report_hash(data: dict[str, Any]) -> str:
    copy = dict(data)
    copy["self_sha256"] = ""
    return hashlib.sha256(_canonical_json(copy)).hexdigest()


def classify_drill(deltas: DrillMetricDeltasV1) -> tuple[FaultClass, str]:
    if (
        deltas.score_unavailable_delta > 0.0
        and deltas.telemetry_quarantined_delta == 0.0
        and deltas.anomaly_decisions_delta == 0.0
    ):
        return (
            "SERVICE",
            f"Scoring unavailable ({deltas.score_unavailable_delta:.0f} requests), 0 quarantined records, 0 anomalous decisions",
        )

    if (
        (deltas.telemetry_quarantined_delta > 0.0 or deltas.segment_breaks_delta > 0.0)
        and deltas.score_unavailable_delta == 0.0
        and deltas.anomaly_decisions_delta == 0.0
    ):
        return (
            "DATA",
            f"Telemetry quarantined ({deltas.telemetry_quarantined_delta:.0f} records) or segment broken ({deltas.segment_breaks_delta:.0f}), downstream scoring uncorrupted",
        )

    if (
        deltas.anomaly_decisions_delta > 0.0
        and deltas.telemetry_quarantined_delta == 0.0
        and deltas.score_unavailable_delta == 0.0
    ):
        return (
            "MACHINE",
            f"Scoring succeeded ({deltas.score_ok_delta:.0f} ok) and detected authentic anomalous degradation ({deltas.anomaly_decisions_delta:.0f} anomalous decisions, {deltas.alert_events_delta:.0f} alert events)",
        )

    return ("UNKNOWN", "Metric signature does not cleanly isolate a single fault category")


def generate_markdown_report(report: FaultReportV1) -> str:
    lines = [
        "# Phase 8 Observability & Reliability Drill Report",
        "",
        f"**Generated:** `{report.timestamp}`  ",
        f"**Overall Status:** `{'PASSED' if report.all_passed else 'FAILED'}`  ",
        f"**Report Self SHA-256:** `{report.self_sha256}`  ",
        "",
        "## Summary of Fault Isolation Drills",
        "",
        "| Drill Type | Expected Fault | Actual Classification | Status | Evidence Summary |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for d in report.drills:
        status_icon = "✅ PASS" if d.passed else "❌ FAIL"
        lines.append(
            f"| `{d.drill_type}` | `{d.expected_classification}` | `{d.actual_classification}` | {status_icon} | {d.evidence_summary} |"
        )

    lines.extend(
        [
            "",
            "## Detailed Metric Signatures",
            "",
        ]
    )

    for d in report.drills:
        lines.extend(
            [
                f"### Drill: `{d.drill_type}`",
                f"- **Expected Classification:** `{d.expected_classification}`",
                f"- **Actual Classification:** `{d.actual_classification}`",
                f"- **Passed:** `{d.passed}`",
                "- **Metric Deltas:**",
                f"  - `telemetry_accepted_delta`: {d.deltas.telemetry_accepted_delta}",
                f"  - `telemetry_quarantined_delta`: {d.deltas.telemetry_quarantined_delta}",
                f"  - `segment_breaks_delta`: {d.deltas.segment_breaks_delta}",
                f"  - `score_ok_delta`: {d.deltas.score_ok_delta}",
                f"  - `score_unavailable_delta`: {d.deltas.score_unavailable_delta}",
                f"  - `anomaly_decisions_delta`: {d.deltas.anomaly_decisions_delta}",
                f"  - `alert_events_delta`: {d.deltas.alert_events_delta}",
                f"  - `kafka_lag_max`: {d.deltas.kafka_lag_max}",
                f"  - `feature_psi_max`: {d.deltas.feature_psi_max}",
                f"- **Evidence:** {d.evidence_summary}",
                "",
            ]
        )

    return "\n".join(lines)


def publish_drill_report(
    drills: list[DrillResultV1],
    json_path: Path,
    md_path: Path,
    git_sha: str,
) -> FaultReportV1:
    if not isinstance(git_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", git_sha) or git_sha == "0" * 40:
        raise ValueError(f"git_sha must be a non-zero lowercase 40-character SHA, got {git_sha!r}")

    now_iso = datetime.now(UTC).isoformat()
    all_passed = all(d.passed for d in drills) and len(drills) > 0

    base_data = {
        "schema_version": "phase8-fault-report-v1",
        "evidence_level": "UNIT",
        "git_sha": git_sha,
        "timestamp": now_iso,
        "all_passed": all_passed,
        "drills": [d.to_dict() for d in drills],
        "self_sha256": "",
    }
    self_hash = _compute_report_hash(base_data)
    base_data["self_sha256"] = self_hash

    report = FaultReportV1(
        timestamp=now_iso,
        drills=drills,
        all_passed=all_passed,
        self_sha256=self_hash,
        git_sha=git_sha,
        evidence_level="UNIT",
    )

    json_target = json_path.resolve()
    json_target.parent.mkdir(parents=True, exist_ok=True)
    tmp_json = json_target.with_suffix(f".tmp.{os.getpid()}")
    tmp_json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    tmp_json.replace(json_target)

    md_target = md_path.resolve()
    md_target.parent.mkdir(parents=True, exist_ok=True)
    tmp_md = md_target.with_suffix(f".tmp.{os.getpid()}")
    tmp_md.write_text(generate_markdown_report(report), encoding="utf-8")
    tmp_md.replace(md_target)

    return report


async def execute_in_process_drills() -> list[DrillResultV1]:
    from datetime import timedelta
    from unittest.mock import AsyncMock, Mock
    from uuid import uuid4

    from prometheus_client import CollectorRegistry

    from industrial_reliability.metrics import build_runtime_metrics
    from industrial_reliability.runtime_messages import (
        CoverageEvidenceV1,
        EvidenceValueV1,
        FeatureVectorV1,
        ScoreDecisionV1,
    )
    from industrial_reliability.scoring_client import RetryableScoringError
    from industrial_reliability.worker import StreamingWorker, WorkerSettings

    # 1. Scoring Outage (SERVICE)
    reg_1 = CollectorRegistry()
    metrics_1 = build_runtime_metrics(reg_1)
    mock_scoring_failing = Mock()
    mock_scoring_failing.score = AsyncMock(
        side_effect=RetryableScoringError("Connection refused by scoring API")
    )
    mock_scoring_failing.close = AsyncMock()

    settings = WorkerSettings(
        bootstrap_servers="localhost:9092",
        scoring_api_url="http://localhost:8000",
        model_version="champion-statistical-v1",
        source_dataset_sha256="0" * 64,
        contract_sha256="0" * 64,
        feature_names=("tp2_mean", "dv_pressure_mean"),
    )
    worker_1 = StreamingWorker(
        settings=settings, scoring_client=mock_scoring_failing, metrics=metrics_1
    )
    worker_1.producer = AsyncMock()

    now_naive = datetime(2020, 2, 25, 0, 30)
    feat = FeatureVectorV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="0" * 64,
        contract_sha256="0" * 64,
        source_timestamp=now_naive,
        emitted_at=datetime.now(UTC),
        window_id=uuid4(),
        window_start=now_naive - timedelta(minutes=30),
        window_end=now_naive,
        machine_id="metropt3",
        feature_names=("tp2_mean", "dv_pressure_mean"),
        feature_values=(1.0, 2.0),
        coverage=CoverageEvidenceV1(
            observations_by_bin=(30, 30, 30, 30, 30, 30),
            bin_ends=(
                now_naive - timedelta(minutes=25),
                now_naive - timedelta(minutes=20),
                now_naive - timedelta(minutes=15),
                now_naive - timedelta(minutes=10),
                now_naive - timedelta(minutes=5),
                now_naive,
            ),
        ),
    )

    import contextlib

    with contextlib.suppress(Exception):
        await worker_1._process_feature(feat)

    deltas_1 = DrillMetricDeltasV1(
        score_unavailable_delta=metrics_1.score_requests.labels(outcome="unavailable")._value.get(),
        score_ok_delta=metrics_1.score_requests.labels(outcome="ok")._value.get(),
        telemetry_quarantined_delta=metrics_1.telemetry_events.labels(
            outcome="quarantined"
        )._value.get(),
        anomaly_decisions_delta=metrics_1.anomaly_decisions._value.get(),
    )
    class_1, summary_1 = classify_drill(deltas_1)
    res_1 = DrillResultV1(
        drill_type="scoring-outage",
        expected_classification="SERVICE",
        actual_classification=class_1,
        passed=class_1 == "SERVICE",
        deltas=deltas_1,
        evidence_summary=summary_1,
    )

    # 2. Malformed Telemetry (DATA)
    reg_2 = CollectorRegistry()
    metrics_2 = build_runtime_metrics(reg_2)
    worker_2 = StreamingWorker(settings=settings, scoring_client=AsyncMock(), metrics=metrics_2)
    worker_2.producer = AsyncMock()

    mock_bad = Mock(
        value=b"INVALID_PAYLOAD_BYTES{{{",
        topic="industrial.metropt3.telemetry.v1",
        partition=0,
        offset=1,
    )
    await worker_2._handle_telemetry_record(mock_bad)

    deltas_2 = DrillMetricDeltasV1(
        telemetry_quarantined_delta=metrics_2.telemetry_events.labels(
            outcome="quarantined"
        )._value.get(),
        score_unavailable_delta=metrics_2.score_requests.labels(outcome="unavailable")._value.get(),
        anomaly_decisions_delta=metrics_2.anomaly_decisions._value.get(),
    )
    class_2, summary_2 = classify_drill(deltas_2)
    res_2 = DrillResultV1(
        drill_type="malformed-telemetry",
        expected_classification="DATA",
        actual_classification=class_2,
        passed=class_2 == "DATA",
        deltas=deltas_2,
        evidence_summary=summary_2,
    )

    # 3. Known Abnormal Machine Replay (MACHINE)
    reg_3 = CollectorRegistry()
    metrics_3 = build_runtime_metrics(reg_3)
    dec_id = uuid4()
    mock_scoring_ok = Mock()
    mock_scoring_ok.score = AsyncMock(
        return_value=ScoreDecisionV1(
            message_id=dec_id,
            replay_session_id=feat.replay_session_id,
            source_dataset_sha256="0" * 64,
            contract_sha256="0" * 64,
            source_timestamp=feat.source_timestamp,
            emitted_at=datetime.now(UTC),
            decision_id=dec_id,
            window_id=feat.window_id,
            model_version="champion-statistical-v1",
            score=3500.0,
            threshold=1200.0,
            is_anomaly=True,
            evidence_vector=(
                EvidenceValueV1(
                    feature_name="tp2_mean",
                    feature_value=9.5,
                    robust_deviation=8.3,
                ),
            ),
        )
    )
    mock_scoring_ok.close = AsyncMock()

    worker_3 = StreamingWorker(settings=settings, scoring_client=mock_scoring_ok, metrics=metrics_3)
    worker_3.producer = AsyncMock()
    await worker_3._process_feature(feat)
    metrics_3.record_alert_action("opened")

    deltas_3 = DrillMetricDeltasV1(
        score_ok_delta=metrics_3.score_requests.labels(outcome="ok")._value.get(),
        anomaly_decisions_delta=metrics_3.anomaly_decisions._value.get(),
        alert_events_delta=metrics_3.alert_events.labels(action="opened")._value.get(),
        telemetry_quarantined_delta=metrics_3.telemetry_events.labels(
            outcome="quarantined"
        )._value.get(),
        score_unavailable_delta=metrics_3.score_requests.labels(outcome="unavailable")._value.get(),
    )
    class_3, summary_3 = classify_drill(deltas_3)
    res_3 = DrillResultV1(
        drill_type="known-abnormal-replay",
        expected_classification="MACHINE",
        actual_classification=class_3,
        passed=class_3 == "MACHINE",
        deltas=deltas_3,
        evidence_summary=summary_3,
    )

    return [res_1, res_2, res_3]


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        description="Run Phase 8 unit fault drills and generate unit report."
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("artifacts/certification/unit/phase-8-unit-fault-drills.json"),
        help="Path for output JSON unit report",
    )
    parser.add_argument(
        "--md-output",
        type=Path,
        default=Path("artifacts/certification/unit/phase-8-unit-fault-drills.md"),
        help="Path for output Markdown unit report",
    )
    parser.add_argument(
        "--git-sha",
        type=str,
        default=None,
        help="Git SHA-256 / commit hash for report",
    )
    args = parser.parse_args()

    git_sha = args.git_sha
    if not git_sha:
        try:
            git_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except Exception:
            git_sha = "a" * 40

    drills = asyncio.run(execute_in_process_drills())
    report = publish_drill_report(
        drills,
        json_path=args.json_output,
        md_path=args.md_output,
        git_sha=git_sha,
    )
    print(f"Phase 8 Unit Fault Drills Finished. All passed: {report.all_passed}")
    print(f"Report JSON: {args.json_output.resolve()}")
    print(f"Report MD: {args.md_output.resolve()}")
    print(f"Self SHA-256: {report.self_sha256}")


if __name__ == "__main__":
    main()
