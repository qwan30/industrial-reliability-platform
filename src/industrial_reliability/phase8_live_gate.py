"""Phase 8 fault-isolation certification gate.

The gate re-runs the shared in-process fault drills with research-candidate
worker settings and publishes them as certification evidence. The drills drive
the real ``StreamingWorker`` fault-isolation logic against isolated Prometheus
metric registries with in-process scoring-client and producer doubles; no
Kafka broker, scoring API, or PostgreSQL is contacted. Reports therefore
publish ``evidence_level: IN_PROCESS`` with an explicit
``simulated_components`` disclosure instead of claiming live evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from industrial_reliability.fault_report import (
    DrillResultV1,
    FaultReportV1,
    build_drill_settings,
    build_fault_report,
    run_known_abnormal_replay_drill,
    run_malformed_telemetry_drill,
    run_scoring_outage_drill,
)
from industrial_reliability.report_hashes import resolve_git_sha

logger = logging.getLogger(__name__)

PHASE8_IN_PROCESS_SCHEMA = "phase8-in-process-fault-drills-v1"
PHASE8_GATE_MODEL_VERSION = "research-statistical-v1"
PHASE8_REPORT_BASENAME = "phase-8-in-process-fault-drills"


async def execute_live_drills() -> list[DrillResultV1]:
    """Run the three fault drills in-process with research-candidate settings."""
    settings = build_drill_settings(model_version=PHASE8_GATE_MODEL_VERSION)
    return [
        await run_scoring_outage_drill(settings),
        await run_malformed_telemetry_drill(settings),
        await run_known_abnormal_replay_drill(settings),
    ]


def publish_live_drill_report(
    drills: list[DrillResultV1],
    json_path: Path,
    md_path: Path,
    git_sha: str,
) -> FaultReportV1:
    """Publish the in-process drill certification report as JSON + Markdown."""
    report = build_fault_report(
        drills,
        git_sha,
        evidence_level="IN_PROCESS",
        schema_version=PHASE8_IN_PROCESS_SCHEMA,
    )

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    return report


def _render_markdown(report: FaultReportV1) -> str:
    md_lines = [
        "# Phase 8 Observability & Reliability Drill Report (In-Process Evidence)",
        "",
        f"- **Verdict:** `{'PASS' if report.all_passed else 'FAIL'}`",
        f"- **Evidence Level:** `{report.evidence_level}`",
        f"- **Simulated Components:** `{', '.join(report.simulated_components)}`",
        f"- **Git SHA:** `{report.git_sha}`",
        f"- **Timestamp:** `{report.timestamp}`",
        f"- **Self SHA-256:** `{report.self_sha256}`",
        "",
        "## Fault Isolation Drill Results",
        "",
        "| Drill Type | Expected | Actual | Status | Summary |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for d in report.drills:
        status_sym = "PASS" if d.passed else "FAIL"
        md_lines.append(
            f"| `{d.drill_type}` | `{d.expected_classification}` | "
            f"`{d.actual_classification}` | **{status_sym}** | {d.evidence_summary} |"
        )

    md_lines.extend(
        [
            "",
            "## Operational Invariants",
            "- Service fault isolates scoring outages without telemetry drop.",
            "- Data fault isolates corrupted telemetry to quarantine without downstream poison.",
            "- Machine fault triggers legitimate stateful alert lifecycle transition.",
            "",
            "## Evidence Disclosure",
            "- Drills execute the real streaming-worker fault-isolation logic in-process.",
            "- Scoring client, Kafka producer, and metrics registry are in-process doubles; "
            "no broker, scoring API, or database is contacted.",
        ]
    )

    return "\n".join(md_lines) + "\n"


def run_phase8_live_gate(
    output_dir: Path | None = None,
    git_sha: str | None = None,
) -> FaultReportV1:
    target_dir = output_dir or Path("artifacts/certification/in_process")
    target_dir.mkdir(parents=True, exist_ok=True)

    sha = resolve_git_sha(git_sha)

    drills = asyncio.run(execute_live_drills())
    json_path = target_dir / f"{PHASE8_REPORT_BASENAME}.json"
    md_path = target_dir / f"{PHASE8_REPORT_BASENAME}.md"
    return publish_live_drill_report(drills, json_path=json_path, md_path=md_path, git_sha=sha)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 8 Fault Drills Certification Gate")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write in-process drill results",
    )
    parser.add_argument(
        "--git-sha",
        type=str,
        default=None,
        help="Committed git SHA",
    )
    args = parser.parse_args(argv)
    report = run_phase8_live_gate(output_dir=args.output_dir, git_sha=args.git_sha)
    print(
        f"Phase 8 Fault Gate: {'PASS' if report.all_passed else 'FAIL'} "
        f"({len(report.drills)} drills executed, evidence_level={report.evidence_level})"
    )
    print(f"Report SHA-256: {report.self_sha256}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
