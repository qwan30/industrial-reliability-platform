"""Release certification and portfolio packaging validation."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from industrial_reliability.report_hashes import compute_self_hash

ReleaseVerdict = Literal["FEASIBLE_PLATFORM_RELEASE", "NEGATIVE_RESEARCH_RELEASE", "INVALID"]

_SELF_HASH_FIELDS = ("report_sha256", "self_sha256")
_RELEASE_EVIDENCE_LEVELS = frozenset({"INTEGRATION", "LIVE"})

_CURRENT_SCHEMAS = frozenset(
    {
        "phase8-live-fault-drills-v1",
        "phase-9-rca-openai-v1",
        "phase-9-rca-fallback-v1",
    }
)

_P8_EVIDENCE_SPECS = {
    "phase-8-live-fault-drills.json": (
        "phase8-live-fault-drills-v1",
        "verdict",
        "PASS",
    )
}

_P9_EVIDENCE_SPECS = {
    "phase-9-rca-openai.json": ("phase-9-rca-openai-v1", "verdict", "PASS"),
    "phase-9-rca-fallback.json": ("phase-9-rca-fallback-v1", "verdict", "PASS"),
}

_P9_PROVIDER_MODES = {
    "phase-9-rca-openai.json": "LIVE_OPENAI",
    "phase-9-rca-fallback.json": "FALLBACK_ONLY",
}


def _load_json_report(file_path: Path) -> dict[str, Any] | None:
    """Load a JSON certification report, returning None when unreadable."""
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _verify_report_self_hash(data: dict[str, Any]) -> bool:
    """Verify the embedded self-hash when the report schema requires one.

    Current certification schemas always embed ``report_sha256`` or
    ``self_sha256``; a missing, malformed, or mismatched hash fails closed.
    Only legacy schemas without a self-hash field may omit it.
    """
    hash_field = next((field for field in _SELF_HASH_FIELDS if field in data), None)
    if hash_field is None:
        return data.get("schema_version") not in _CURRENT_SCHEMAS
    stored = data[hash_field]
    if not isinstance(stored, str) or len(stored) != 64:
        return False
    return hmac.compare_digest(stored, compute_self_hash(data, hash_field))


def _report_matches_git_sha(data: dict[str, Any], git_sha: str) -> bool:
    """Exact-SHA certification: evidence must be bound to the certified commit.

    Current schemas always embed ``git_sha`` and it must equal the resolved
    SHA, so evidence produced for a different commit is rejected. Legacy
    reports without the field remain accepted for backward compatibility.
    """
    if "git_sha" in data:
        return data.get("git_sha") == git_sha
    return data.get("schema_version") not in _CURRENT_SCHEMAS


def _verify_release_evidence(
    data: dict[str, Any] | None,
    expected_schema: str,
    verdict_field: str,
    passing_value: Any,
    git_sha: str,
    expected_provider_mode: str | None = None,
) -> bool:
    """Validate one certification report as release evidence.

    The report must match the schema bound to its filename, carry a passing
    verdict, disclose gate-level evidence (INTEGRATION or LIVE), carry a valid
    embedded self-hash, match expected provider mode if set, and be bound to
    the certified commit.
    """
    if data is None:
        return False
    return (
        data.get("schema_version") == expected_schema
        and data.get(verdict_field) == passing_value
        and data.get("evidence_level") in _RELEASE_EVIDENCE_LEVELS
        and (expected_provider_mode is None or data.get("provider_mode") == expected_provider_mode)
        and _verify_report_self_hash(data)
        and _report_matches_git_sha(data, git_sha)
    )


@dataclass(frozen=True)
class ReleaseCertificationReportV1:
    schema_version: str
    timestamp: str
    git_sha: str
    verdict: ReleaseVerdict
    phases_passed: list[str]
    decision_gates: dict[str, str]
    artifact_hashes: dict[str, str]
    is_certified: bool
    limitations: list[str]
    report_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_git_sha(git_sha: str | None) -> str:
    if git_sha is not None:
        return git_sha
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return ""


def _collect_decision_gates(
    artifact_dir: Path,
    decision_gates: dict[str, str],
    artifact_hashes: dict[str, str],
) -> None:
    p7a_file = artifact_dir / "phase-7a-airflow-decision.json"
    if p7a_file.is_file():
        data = json.loads(p7a_file.read_text(encoding="utf-8"))
        decision_gates["airflow"] = data.get("decision", "NOT_ADOPTED")
    elif Path("docs/decisions/2026-08-24-airflow-not-adopted.md").is_file():
        decision_gates["airflow"] = "NOT_ADOPTED"

    p10a_file = artifact_dir / "phase-10a-spark-decision.json"
    if p10a_file.is_file():
        data = json.loads(p10a_file.read_text(encoding="utf-8"))
        decision_gates["spark"] = data.get("status", "N/A")
        artifact_hashes["phase10a_spark"] = hashlib.sha256(p10a_file.read_bytes()).hexdigest()

    p10b_file = artifact_dir / "phase-10b-openvino-decision.json"
    if p10b_file.is_file():
        data = json.loads(p10b_file.read_text(encoding="utf-8"))
        decision_gates["openvino"] = data.get("status", "N/A")
        artifact_hashes["phase10b_openvino"] = hashlib.sha256(p10b_file.read_bytes()).hexdigest()


class ReleaseCertificationValidator:
    def __init__(self, artifact_dir: Path | str = Path("docs/results")) -> None:
        self.artifact_dir = Path(artifact_dir)

    def evaluate(self, git_sha: str | None = None) -> ReleaseCertificationReportV1:
        resolved_sha = _resolve_git_sha(git_sha)

        if (
            not resolved_sha
            or not re.fullmatch(r"[0-9a-f]{40}", resolved_sha)
            or resolved_sha == "0" * 40
        ):
            return ReleaseCertificationReportV1(
                schema_version="release-certification-v1",
                timestamp=datetime.now(UTC).isoformat(),
                git_sha=resolved_sha or "0" * 40,
                verdict="INVALID",
                phases_passed=[],
                decision_gates={},
                artifact_hashes={},
                is_certified=False,
                limitations=[
                    "Exact committed 40-character lowercase hex git_sha required; fail closed"
                ],
            )

        if not self.artifact_dir.exists():
            return ReleaseCertificationReportV1(
                schema_version="release-certification-v1",
                timestamp=datetime.now(UTC).isoformat(),
                git_sha=resolved_sha,
                verdict="INVALID",
                phases_passed=[],
                decision_gates={},
                artifact_hashes={},
                is_certified=False,
                limitations=["Artifact directory missing"],
            )

        phases_passed: list[str] = []
        decision_gates: dict[str, str] = {}
        artifact_hashes: dict[str, str] = {}
        limitations: list[str] = []

        # 1. Check Phase 1 / Phase 1B
        p1b_file = self.artifact_dir / "phase-1b-metrics.json"
        is_feasible = False
        phase1b_valid = False
        if p1b_file.is_file():
            data = _load_json_report(p1b_file)
            if data is not None and data.get("schema_version") == "phase1b-benchmark-v1":
                artifact_hashes["phase1b_metrics"] = hashlib.sha256(
                    p1b_file.read_bytes()
                ).hexdigest()
                phase1b_valid = True
                if data.get("verdict") == "FEASIBLE":
                    is_feasible = True
                    phases_passed.append("phase1b")
                else:
                    phases_passed.append("phase1b_negative_benchmark")
                    limitations.append(
                        "Phase 1B offline ML feasibility did not meet event detection/false alarm gates on MetroPT-3 holdout."
                    )
        if not phase1b_valid:
            limitations.append("Phase 1B metrics missing or invalid schema; phase not certified.")

        # 2. Check Decision Gates
        _collect_decision_gates(self.artifact_dir, decision_gates, artifact_hashes)

        # 3. Check Phase 8 Observability & Fault drills
        phase8_valid = False
        for filename, (schema, verdict_field, passing_val) in _P8_EVIDENCE_SPECS.items():
            candidate = self.artifact_dir / filename
            if candidate.is_file():
                if _verify_release_evidence(
                    _load_json_report(candidate),
                    schema,
                    verdict_field,
                    passing_val,
                    resolved_sha,
                ):
                    phase8_valid = True
                    phases_passed.append("phase8_observability_fault_drills")
                    artifact_hashes["phase8_observability"] = hashlib.sha256(
                        candidate.read_bytes()
                    ).hexdigest()
                break
        if not phase8_valid:
            limitations.append(
                "Phase 8 fault-drill evidence missing, failing, unreadable, tampered, "
                "unit-level, or bound to a different commit; phase not certified."
            )

        # 4. Check Phase 9 Grounded RCA
        phase9_valid = False
        for filename, (schema, verdict_field, passing_val) in _P9_EVIDENCE_SPECS.items():
            candidate = self.artifact_dir / filename
            if candidate.is_file():
                expected_mode = _P9_PROVIDER_MODES.get(filename)
                if _verify_release_evidence(
                    _load_json_report(candidate),
                    schema,
                    verdict_field,
                    passing_val,
                    resolved_sha,
                    expected_provider_mode=expected_mode,
                ):
                    phase9_valid = True
                    phases_passed.append("phase9_grounded_rca")
                    artifact_hashes["phase9_rca"] = hashlib.sha256(
                        candidate.read_bytes()
                    ).hexdigest()
                break
        if not phase9_valid:
            limitations.append(
                "Phase 9 grounded-RCA evidence missing, failing, unreadable, tampered, "
                "unit-level, or bound to a different commit; phase not certified."
            )

        # Determine aggregate verdict
        mandatory_evidence_valid = phase1b_valid and phase8_valid and phase9_valid
        verdict: ReleaseVerdict = (
            "FEASIBLE_PLATFORM_RELEASE"
            if mandatory_evidence_valid and is_feasible
            else "NEGATIVE_RESEARCH_RELEASE"
            if mandatory_evidence_valid
            else "INVALID"
        )
        is_certified = mandatory_evidence_valid
        if mandatory_evidence_valid and not is_feasible:
            limitations.append(
                "Platform models demonstrated offline event detection tradeoffs and are packaged as negative research findings."
            )

        report_dict: dict[str, Any] = {
            "schema_version": "release-certification-v1",
            "timestamp": datetime.now(UTC).isoformat(),
            "git_sha": resolved_sha,
            "verdict": verdict,
            "phases_passed": phases_passed,
            "decision_gates": decision_gates,
            "artifact_hashes": artifact_hashes,
            "is_certified": is_certified,
            "limitations": limitations,
            "report_sha256": "",
        }

        report_sha256 = compute_self_hash(report_dict, "report_sha256")
        report_dict["report_sha256"] = report_sha256

        return ReleaseCertificationReportV1(
            schema_version=report_dict["schema_version"],
            timestamp=report_dict["timestamp"],
            git_sha=report_dict["git_sha"],
            verdict=report_dict["verdict"],
            phases_passed=report_dict["phases_passed"],
            decision_gates=report_dict["decision_gates"],
            artifact_hashes=report_dict["artifact_hashes"],
            is_certified=report_dict["is_certified"],
            limitations=report_dict["limitations"],
            report_sha256=report_dict["report_sha256"],
        )


def run_release_certification(
    *,
    artifact_dir: Path = Path("docs/results"),
    output_file: Path = Path("docs/results/release-certification.json"),
    git_sha: str | None = None,
) -> ReleaseCertificationReportV1:
    validator = ReleaseCertificationValidator(artifact_dir=artifact_dir)
    report = validator.evaluate(git_sha=git_sha)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    md_path = output_file.with_suffix(".md")
    md_lines = [
        "# Release Certification & Portfolio Packaging Report",
        "",
        f"- **Verdict:** `{report.verdict}`",
        f"- **Certified:** `{report.is_certified}`",
        f"- **Git SHA:** `{report.git_sha}`",
        f"- **Certified At:** `{report.timestamp}`",
        f"- **Report SHA-256:** `{report.report_sha256}`",
        "",
        "## Phases & Gates Summary",
        f"- **Phases Certified:** {', '.join(report.phases_passed)}",
        f"- **Decision Gates:** {json.dumps(report.decision_gates)}",
        "",
        "## Artifact Hashes",
        "| Artifact | SHA-256 |",
        "| :--- | :--- |",
    ]
    for name, sha in sorted(report.artifact_hashes.items()):
        md_lines.append(f"| `{name}` | `{sha}` |")

    md_lines.extend(
        [
            "",
            "## Limitations & Research Findings",
        ]
    )
    for lim in report.limitations:
        md_lines.append(f"- {lim}")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release Certification & Portfolio Packaging")
    parser.add_argument("--artifact-dir", type=Path, default=Path("docs/results"))
    parser.add_argument(
        "--output", type=Path, default=Path("docs/results/release-certification.json")
    )
    parser.add_argument("--git-sha", type=str, default=None)

    args = parser.parse_args(argv)
    report = run_release_certification(
        artifact_dir=args.artifact_dir,
        output_file=args.output,
        git_sha=args.git_sha,
    )
    print(f"Release Certification Verdict: {report.verdict} (Certified: {report.is_certified})")
    print(f"Report SHA-256: {report.report_sha256}")
    return 0 if report.is_certified else 1


if __name__ == "__main__":
    sys.exit(main())
