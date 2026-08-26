"""Phase 9 grounded RCA contract gate (unit-evidence verification).

Runs the shared Phase 9 contract checks entirely in-process against doubles
and publishes a report with ``evidence_level: UNIT`` and ``provider_mode:
MOCKED_CONTRACT``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from industrial_reliability.rca_gate_checks import (
    build_gate_report,
    check_allowlisted_evidence_projection,
    check_citation_enforcement,
    check_openai_sdk_parse_support,
    check_provider_generation_and_fallback,
    check_secret_isolation_from_env,
    render_gate_markdown,
)
from industrial_reliability.report_hashes import resolve_git_sha

PHASE9_CONTRACT_SIMULATED_COMPONENTS = (
    "alert store (in-process double)",
    "OpenAI client (in-process double; no live API calls)",
)
PHASE9_CONTRACT_INVARIANTS = (
    "Pinned OpenAI SDK structured outputs verified with `responses.parse`.",
    "4 Allowlisted projection tools strictly enforced: `get_alert`, "
    "`get_score_evidence`, `get_model_provenance`, `get_system_health`.",
    "Closed-world grounding guarantees all observation citations exist in the input bundle.",
    "Graceful fallback guarantees `UNAVAILABLE` evidence-only output on provider outage "
    "without blocking triage.",
    "Zero telemetry leakage, raw rows excluded, and credentials scrubbed from all logging "
    "and metrics.",
)


class Phase9CertificationGate:
    """Runs the in-process Phase 9 RCA contract checks with mocked providers."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def record_check(self, name: str, passed: bool, details: str) -> None:
        self.checks.append(
            {
                "name": name,
                "passed": passed,
                "details": details,
            }
        )

    def _record(self, name: str, result: tuple[bool, str]) -> None:
        passed, details = result
        self.record_check(name, passed, details)

    def run_all_checks(self) -> bool:
        # Check 1: Pinned OpenAI SDK structured outputs support
        self._record(
            "openai_sdk_responses_parse_support",
            check_openai_sdk_parse_support("test-key-mock"),
        )

        # Check 2: 4-tool allowlisted evidence projection
        self._record("allowlisted_evidence_projection", check_allowlisted_evidence_projection())

        # Check 3: Citation enforcement and closed-world grounding
        self._record("citation_enforcement_contract", check_citation_enforcement("gpt-4o"))

        # Check 4: Provider complete generation and fallback paths
        self._record(
            "provider_generation_and_fallback",
            check_provider_generation_and_fallback("gpt-4o"),
        )

        # Check 5: Secret isolation & zero key leakage
        self._record("secret_isolation_and_scrubbing", check_secret_isolation_from_env())

        return all(c["passed"] for c in self.checks)

    def generate_report(self, git_sha: str) -> dict[str, Any]:
        return build_gate_report(
            git_sha=git_sha,
            schema_version="phase-9-rca-contract-v1",
            evidence_level="UNIT",
            provider_mode="MOCKED_CONTRACT",
            simulated_components=PHASE9_CONTRACT_SIMULATED_COMPONENTS,
            checks=self.checks,
        )


def run_phase9_gate(
    output_dir: Path | None = None,
    git_sha: str | None = None,
) -> dict[str, Any]:
    target_dir = output_dir or Path("artifacts/certification/unit")
    target_dir.mkdir(parents=True, exist_ok=True)

    sha = resolve_git_sha(git_sha)

    gate = Phase9CertificationGate()
    gate.run_all_checks()
    report = gate.generate_report(git_sha=sha)

    json_path = target_dir / "phase-9-contract-gate.json"
    md_path = target_dir / "phase-9-contract-gate.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(
        render_gate_markdown(
            report,
            "# Phase 9: Grounded Root-Cause Analysis (RCA) — Contract Gate Report",
            "## Certified Contract & Security Invariants",
            PHASE9_CONTRACT_INVARIANTS,
        ),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 9 Grounded RCA Contract Gate")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write contract results (default: artifacts/certification/unit)",
    )
    parser.add_argument(
        "--git-sha",
        type=str,
        default=None,
        help="Git SHA of the committed code",
    )
    args = parser.parse_args(argv)
    report = run_phase9_gate(output_dir=args.output_dir, git_sha=args.git_sha)
    print(
        f"Phase 9 Contract Gate: {report['verdict']} "
        f"({report['passed_checks']}/{report['total_checks']} passed)"
    )
    print(f"Report SHA-256: {report['report_sha256']}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
