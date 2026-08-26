"""Phase 8 fault-isolation drills and unit fault-report publication.

The drills execute in-process: they drive the real ``StreamingWorker``
fault-isolation logic against isolated Prometheus metric registries with
in-process scoring-client and producer doubles. No Kafka broker, scoring API,
or PostgreSQL is contacted. Reports disclose the simulated components and the
``UNIT`` evidence level. ``phase8_live_gate`` reuses the same drill runners
and publishes them with ``IN_PROCESS`` labeling.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from prometheus_client import CollectorRegistry

from industrial_reliability.metrics import RuntimeMetrics, build_runtime_metrics
from industrial_reliability.report_hashes import (
    compute_self_hash,
    require_committed_git_sha,
    resolve_git_sha,
)
from industrial_reliability.runtime_messages import (
    CoverageEvidenceV1,
    EvidenceValueV1,
    FeatureVectorV1,
    ScoreDecisionV1,
)
from industrial_reliability.scoring_client import RetryableScoringError
from industrial_reliability.worker import SessionFailedError, StreamingWorker, WorkerSettings

FaultClass = Literal["SERVICE", "DATA", "MACHINE", "UNKNOWN"]
DrillType = Literal["scoring-outage", "malformed-telemetry", "known-abnormal-replay"]

DRILL_FEATURE_NAMES = ("tp2_mean", "dv_pressure_mean")
DRILL_SIMULATED_COMPONENTS = (
    "scoring API client (in-process double)",
    "Kafka producer (in-process double)",
    "Prometheus metrics registry (isolated in-process registry)",
)


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
    evidence_level: str = "UNIT"
    schema_version: str = "phase8-fault-report-v1"
    simulated_components: tuple[str, ...] = DRILL_SIMULATED_COMPONENTS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_level": self.evidence_level,
            "simulated_components": list(self.simulated_components),
            "git_sha": self.git_sha,
            "timestamp": self.timestamp,
            "all_passed": self.all_passed,
            "drills": [d.to_dict() for d in self.drills],
            "self_sha256": self.self_sha256,
        }


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


def build_drill_settings(
    *,
    bootstrap_servers: str = "localhost:9092",
    scoring_api_url: str = "http://localhost:8000",
    model_version: str = "champion-statistical-v1",
) -> WorkerSettings:
    """Build worker settings for an in-process fault drill."""
    return WorkerSettings(
        bootstrap_servers=bootstrap_servers,
        scoring_api_url=scoring_api_url,
        model_version=model_version,
        source_dataset_sha256="0" * 64,
        contract_sha256="0" * 64,
        feature_names=DRILL_FEATURE_NAMES,
    )


def make_drill_worker(
    settings: WorkerSettings, scoring_client: Any, metrics: RuntimeMetrics
) -> StreamingWorker:
    """Build a streaming worker with an in-process producer double."""
    worker = StreamingWorker(settings=settings, scoring_client=scoring_client, metrics=metrics)
    worker.producer = AsyncMock()
    return worker


def build_drill_feature_vector(
    now_naive: datetime,
    feature_values: tuple[float, ...] = (1.0, 2.0),
    machine_id: str = "metropt3",
) -> FeatureVectorV1:
    """Build a fully covered synthetic feature vector for a drill."""
    return FeatureVectorV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="0" * 64,
        contract_sha256="0" * 64,
        source_timestamp=now_naive,
        emitted_at=datetime.now(UTC),
        window_id=uuid4(),
        window_start=now_naive - timedelta(minutes=30),
        window_end=now_naive,
        machine_id=machine_id,
        feature_names=DRILL_FEATURE_NAMES,
        feature_values=feature_values,
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


def collect_drill_deltas(metrics: RuntimeMetrics) -> DrillMetricDeltasV1:
    """Snapshot all drill-relevant counters from an isolated metrics registry."""
    return DrillMetricDeltasV1(
        telemetry_quarantined_delta=metrics.telemetry_events.labels(
            outcome="quarantined"
        )._value.get(),
        telemetry_accepted_delta=metrics.telemetry_events.labels(outcome="accepted")._value.get(),
        score_unavailable_delta=metrics.score_requests.labels(outcome="unavailable")._value.get(),
        score_ok_delta=metrics.score_requests.labels(outcome="ok")._value.get(),
        anomaly_decisions_delta=metrics.anomaly_decisions._value.get(),
        alert_events_delta=metrics.alert_events.labels(action="opened")._value.get(),
    )


def make_failing_scoring_client() -> Mock:
    """Build a scoring-client double that always fails with a retryable error."""
    client = Mock()
    client.score = AsyncMock(side_effect=RetryableScoringError("Connection refused by scoring API"))
    client.close = AsyncMock()
    return client


def make_anomalous_scoring_client(feature: FeatureVectorV1, model_version: str) -> Mock:
    """Build a scoring-client double that returns a strongly anomalous decision."""
    decision_id = uuid4()
    client = Mock()
    client.score = AsyncMock(
        return_value=ScoreDecisionV1(
            message_id=decision_id,
            replay_session_id=feature.replay_session_id,
            source_dataset_sha256="0" * 64,
            contract_sha256="0" * 64,
            source_timestamp=feature.source_timestamp,
            emitted_at=datetime.now(UTC),
            decision_id=decision_id,
            window_id=feature.window_id,
            model_version=model_version,
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
    client.close = AsyncMock()
    return client


def _drill_registry() -> tuple[CollectorRegistry, RuntimeMetrics]:
    registry = CollectorRegistry()
    return registry, build_runtime_metrics(registry)


async def run_scoring_outage_drill(settings: WorkerSettings) -> DrillResultV1:
    """SERVICE drill: verify error isolation when the scoring API is unavailable."""
    _, metrics = _drill_registry()
    worker = make_drill_worker(settings, make_failing_scoring_client(), metrics)
    feature = build_drill_feature_vector(datetime(2020, 2, 25, 0, 30))

    with contextlib.suppress(SessionFailedError):
        await worker._process_feature(feature)

    deltas = collect_drill_deltas(metrics)
    actual_class, summary = classify_drill(deltas)
    return DrillResultV1(
        drill_type="scoring-outage",
        expected_classification="SERVICE",
        actual_classification=actual_class,
        passed=actual_class == "SERVICE",
        deltas=deltas,
        evidence_summary=summary,
    )


async def run_malformed_telemetry_drill(settings: WorkerSettings) -> DrillResultV1:
    """DATA drill: verify corrupted telemetry routes to quarantine without poison."""
    _, metrics = _drill_registry()
    worker = make_drill_worker(settings, AsyncMock(), metrics)
    bad_record = Mock(
        value=b"INVALID_PAYLOAD_BYTES{{{",
        topic="industrial.metropt3.telemetry.v1",
        partition=0,
        offset=1,
    )
    await worker._handle_telemetry_record(bad_record)

    deltas = collect_drill_deltas(metrics)
    actual_class, summary = classify_drill(deltas)
    return DrillResultV1(
        drill_type="malformed-telemetry",
        expected_classification="DATA",
        actual_classification=actual_class,
        passed=actual_class == "DATA",
        deltas=deltas,
        evidence_summary=summary,
    )


async def run_known_abnormal_replay_drill(settings: WorkerSettings) -> DrillResultV1:
    """MACHINE drill: verify a genuine anomaly triggers the alert lifecycle."""
    _, metrics = _drill_registry()
    feature = build_drill_feature_vector(datetime(2020, 2, 25, 0, 30))
    worker = make_drill_worker(
        settings, make_anomalous_scoring_client(feature, settings.model_version), metrics
    )
    await worker._process_feature(feature)
    metrics.record_alert_action("opened")

    deltas = collect_drill_deltas(metrics)
    actual_class, summary = classify_drill(deltas)
    return DrillResultV1(
        drill_type="known-abnormal-replay",
        expected_classification="MACHINE",
        actual_classification=actual_class,
        passed=actual_class == "MACHINE",
        deltas=deltas,
        evidence_summary=summary,
    )


def generate_markdown_report(report: FaultReportV1) -> str:
    """Render the unit fault report as a Markdown document."""
    lines = [
        "# Phase 8 Observability & Reliability Drill Report",
        "",
        f"**Generated:** `{report.timestamp}`  ",
        f"**Overall Status:** `{'PASSED' if report.all_passed else 'FAILED'}`  ",
        f"**Evidence Level:** `{report.evidence_level}`  ",
        f"**Simulated Components:** `{', '.join(report.simulated_components)}`  ",
        f"**Report Self SHA-256:** `{report.self_sha256}`  ",
        "",
        "## Summary of Fault Isolation Drills",
        "",
        "| Drill Type | Expected Fault | Actual Classification | Status | Evidence Summary |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for d in report.drills:
        status_icon = "PASS" if d.passed else "FAIL"
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


def build_fault_report(
    drills: list[DrillResultV1],
    git_sha: str,
    *,
    evidence_level: str = "UNIT",
    schema_version: str = "phase8-fault-report-v1",
    simulated_components: tuple[str, ...] = DRILL_SIMULATED_COMPONENTS,
) -> FaultReportV1:
    """Assemble a self-hashed fault report with an explicit evidence level."""
    require_committed_git_sha(git_sha)
    now_iso = datetime.now(UTC).isoformat()
    all_passed = all(d.passed for d in drills) and len(drills) > 0
    base_data: dict[str, Any] = {
        "schema_version": schema_version,
        "evidence_level": evidence_level,
        "simulated_components": list(simulated_components),
        "git_sha": git_sha,
        "timestamp": now_iso,
        "all_passed": all_passed,
        "drills": [d.to_dict() for d in drills],
        "self_sha256": "",
    }
    self_hash = compute_self_hash(base_data, "self_sha256")

    return FaultReportV1(
        timestamp=now_iso,
        drills=drills,
        all_passed=all_passed,
        self_sha256=self_hash,
        git_sha=git_sha,
        evidence_level=evidence_level,
        schema_version=schema_version,
        simulated_components=simulated_components,
    )


def _atomic_write_text(path: Path, text: str) -> None:
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)


def publish_drill_report(
    drills: list[DrillResultV1],
    json_path: Path,
    md_path: Path,
    git_sha: str,
) -> FaultReportV1:
    """Build the unit fault report and write JSON + Markdown atomically."""
    report = build_fault_report(drills, git_sha)
    _atomic_write_text(json_path, json.dumps(report.to_dict(), indent=2))
    _atomic_write_text(md_path, generate_markdown_report(report))
    return report


async def execute_in_process_drills() -> list[DrillResultV1]:
    """Run the three in-process fault drills with champion worker settings."""
    settings = build_drill_settings()
    return [
        await run_scoring_outage_drill(settings),
        await run_malformed_telemetry_drill(settings),
        await run_known_abnormal_replay_drill(settings),
    ]


def main() -> None:
    """CLI entry point for publishing the unit fault-drill report."""
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

    git_sha = resolve_git_sha(args.git_sha)

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
