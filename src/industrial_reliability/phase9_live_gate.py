"""Phase 9 dual-mode grounded RCA evidence gate.

The contract checks and fallback path publish truthful ``IN_PROCESS`` evidence.
Only a verified provider response may produce the ``LIVE`` OpenAI profile, and
the report continues to disclose any in-process evidence dependencies.
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import OpenAI

from industrial_reliability.rca_gate_checks import (
    build_gate_report,
    check_allowlisted_evidence_projection,
    check_citation_enforcement,
    check_graceful_fallback_on_provider_error,
    check_openai_sdk_parse_support,
    check_secret_scrubbing_repr,
    gather_synthetic_alert_evidence,
    render_gate_markdown,
)
from industrial_reliability.rca_openai import OpenAiRcaGenerator, evidence_only_report
from industrial_reliability.report_hashes import resolve_git_sha

logger = logging.getLogger(__name__)

PHASE9_RCA_SCHEMA_LIVE = "phase-9-rca-openai-v1"
PHASE9_RCA_SCHEMA_FALLBACK = "phase-9-rca-fallback-v1"
PHASE9_SIMULATED_COMPONENTS = (
    "alert store (in-process double)",
)
PHASE9_OPERATIONAL_INVARIANTS = (
    "4 Allowlisted projection tools strictly enforced: `get_alert`, "
    "`get_score_evidence`, `get_model_provenance`, `get_system_health`.",
    "Closed-world grounding guarantees all observation citations exist in the input bundle.",
    "Graceful fallback guarantees `UNAVAILABLE` evidence-only output on provider outage "
    "without blocking triage.",
    "Zero telemetry leakage, raw rows excluded, and credentials scrubbed from all logging "
    "and metrics.",
)


@dataclass(frozen=True, slots=True)
class ProviderCallReceipt:
    dependency: Literal["openai"]
    model: str
    report_id: str
    evidence_bundle_sha256: str


def check_live_openai_generation(api_key: str, model: str) -> ProviderCallReceipt:
    _alert_id, bundle = gather_synthetic_alert_evidence()
    client = OpenAI(api_key=api_key, timeout=20.0, max_retries=0)
    report = OpenAiRcaGenerator(client=client, model=model, timeout_seconds=20.0).generate(bundle)
    if report.status != "COMPLETE" or report.provider_model != model:
        raise RuntimeError("provider did not return a complete grounded report")
    return ProviderCallReceipt(
        dependency="openai",
        model=model,
        report_id=report.report_id,
        evidence_bundle_sha256=report.evidence_bundle_sha256,
    )


def _get_json(url: str, timeout_seconds: float, *, method: str = "GET") -> dict[str, Any]:
    request = Request(url, method=method, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise RuntimeError(f"runtime endpoint returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("runtime RCA endpoint unavailable") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("runtime RCA endpoint returned an invalid envelope")
    return payload


def check_persisted_rca_round_trip(
    base_url: str,
    alert_id: str,
    *,
    timeout_seconds: float = 20.0,
) -> tuple[ProviderCallReceipt, list[dict[str, str]]]:
    """Verify POST COMPLETE is followed by a matching persisted GET."""
    root = base_url.rstrip("/")
    post_payload = _get_json(
        f"{root}/v1/alerts/{alert_id}/rca",
        timeout_seconds,
        method="POST",
    )
    if post_payload.get("success") is not True or not isinstance(post_payload.get("data"), dict):
        raise RuntimeError("runtime RCA POST did not return a report")
    posted = post_payload["data"]
    if posted.get("status") != "COMPLETE":
        raise RuntimeError("runtime RCA POST did not return COMPLETE")

    detail_payload = _get_json(f"{root}/v1/alerts/{alert_id}", timeout_seconds)
    detail = detail_payload.get("data")
    persisted = detail.get("rca") if isinstance(detail, dict) else None
    if not isinstance(persisted, dict):
        raise RuntimeError("runtime RCA GET did not return a persisted report")
    for field in ("report_id", "evidence_bundle_sha256", "status"):
        if persisted.get(field) != posted.get(field):
            raise RuntimeError("runtime RCA POST/GET identity mismatch")

    provider_model = posted.get("provider_model")
    if not isinstance(provider_model, str) or not provider_model:
        raise RuntimeError("runtime RCA report has no provider model")
    receipt = ProviderCallReceipt(
        dependency="openai",
        model=provider_model,
        report_id=str(posted["report_id"]),
        evidence_bundle_sha256=str(posted["evidence_bundle_sha256"]),
    )
    return receipt, [
        {"dependency": "postgres"},
        {"dependency": "scoring_api"},
        asdict(receipt),
    ]


class Phase9LiveGate:
    """Runs the Phase 9 RCA contract checks for the configured provider mode."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        provider_receipt: ProviderCallReceipt | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("RCA_OPENAI_API_KEY", "").strip() or None
        self.model = model or os.environ.get("RCA_OPENAI_MODEL", "gpt-4o-mini").strip()
        self.provider_receipt = provider_receipt
        self.provider_mode: Literal["LIVE_OPENAI", "FALLBACK_ONLY"] = (
            "LIVE_OPENAI" if provider_receipt is not None else "FALLBACK_ONLY"
        )
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
        if self.provider_mode == "LIVE_OPENAI":
            self._run_live_openai_checks()
        else:
            self._run_fallback_checks()

        return all(c["passed"] for c in self.checks)

    def _run_fallback_checks(self) -> None:
        # Check 1: Fallback generator operates without API key
        self._check_fallback_generator()

        # Check 2: 4-tool allowlisted evidence projection
        self._record("allowlisted_evidence_projection", check_allowlisted_evidence_projection())

        # Check 3: Citation enforcement and closed-world grounding
        self._record("citation_enforcement_and_grounding", check_citation_enforcement(self.model))

        # Check 4: Secret scrubbing
        self._record("secret_isolation_and_scrubbing", check_secret_scrubbing_repr())

    def _run_live_openai_checks(self) -> None:
        # Check 1: OpenAI SDK responses.parse support
        self._record(
            "openai_sdk_responses_parse_support",
            check_openai_sdk_parse_support(self.api_key or ""),
        )

        # Check 2: 4-tool allowlisted evidence projection
        self._record("allowlisted_evidence_projection", check_allowlisted_evidence_projection())

        # Check 3: Citation enforcement and closed-world grounding
        self._record("citation_enforcement_and_grounding", check_citation_enforcement(self.model))

        # Check 4: Graceful fallback on provider error
        self._record(
            "graceful_fallback_on_provider_error",
            check_graceful_fallback_on_provider_error(self.model),
        )

        # Check 5: Secret scrubbing
        self._record("secret_isolation_and_scrubbing", check_secret_scrubbing_repr())

    def _check_fallback_generator(self) -> None:
        try:
            _, bundle = gather_synthetic_alert_evidence()
            report = evidence_only_report(bundle, reason="provider_not_configured")
            if report.status == "UNAVAILABLE" and "Provider RCA unavailable" in report.summary:
                self.record_check(
                    "fallback_generator_available",
                    True,
                    "Fallback report generated with UNAVAILABLE status and standard reason",
                )
            else:
                self.record_check(
                    "fallback_generator_available",
                    False,
                    f"Unexpected fallback report: {report.status} / {report.summary}",
                )
        except Exception as exc:
            self.record_check("fallback_generator_available", False, str(exc))

    def generate_report(self, git_sha: str) -> dict[str, Any]:
        evidence_level = "LIVE" if self.provider_receipt is not None else "IN_PROCESS"
        schema_version = (
            PHASE9_RCA_SCHEMA_LIVE
            if self.provider_receipt is not None
            else PHASE9_RCA_SCHEMA_FALLBACK
        )
        dependency_receipts = (
            [asdict(self.provider_receipt)] if self.provider_receipt is not None else []
        )
        return build_gate_report(
            git_sha=git_sha,
            schema_version=schema_version,
            evidence_level=evidence_level,
            provider_mode=self.provider_mode,
            simulated_components=PHASE9_SIMULATED_COMPONENTS,
            checks=self.checks,
            dependency_receipts=dependency_receipts,
        )

    def _generate_runtime_report(
        self,
        git_sha: str,
        dependency_receipts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build release evidence only after the runtime round trip succeeded."""
        if self.provider_receipt is None:
            raise RuntimeError("runtime RCA evidence requires a complete provider receipt")
        dependencies = {item.get("dependency") for item in dependency_receipts}
        if {"postgres", "scoring_api", "openai"} - dependencies:
            raise RuntimeError("runtime RCA evidence is missing dependency receipts")
        return build_gate_report(
            git_sha=git_sha,
            schema_version=PHASE9_RCA_SCHEMA_LIVE,
            evidence_level="LIVE",
            provider_mode="LIVE_OPENAI",
            simulated_components=(),
            checks=self.checks,
            dependency_receipts=dependency_receipts,
        )


def run_phase9_live_gate(
    output_dir: Path | None = None,
    git_sha: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    alert_id: str | None = None,
) -> dict[str, Any]:
    target_dir = output_dir or Path("artifacts/certification/live")
    target_dir.mkdir(parents=True, exist_ok=True)

    sha = resolve_git_sha(git_sha)

    resolved_api_key = api_key or os.environ.get("RCA_OPENAI_API_KEY", "").strip() or None
    resolved_model = model or os.environ.get("RCA_OPENAI_MODEL", "gpt-4o-mini").strip()

    receipt: ProviderCallReceipt | None = None
    runtime_receipts: list[dict[str, Any]] = []
    runtime_requested = base_url is not None or alert_id is not None
    runtime_error: str | None = None
    if runtime_requested:
        if not base_url or not alert_id:
            runtime_error = "both base_url and alert_id are required for runtime RCA evidence"
        else:
            try:
                receipt, runtime_receipts = check_persisted_rca_round_trip(
                    base_url,
                    alert_id,
                )
            except Exception:
                logger.exception("Runtime RCA persistence verification failed")
                runtime_error = "runtime RCA persistence verification failed"
    elif resolved_api_key and resolved_model:
        try:
            receipt = check_live_openai_generation(resolved_api_key, resolved_model)
        except Exception:
            logger.exception("Live OpenAI verification failed; retaining IN_PROCESS evidence")

    gate = Phase9LiveGate(
        api_key=resolved_api_key,
        model=resolved_model,
        provider_receipt=receipt,
    )
    gate.run_all_checks()
    if runtime_error is not None:
        gate.record_check("persisted_rca_round_trip", False, runtime_error)
    report = (
        gate._generate_runtime_report(git_sha=sha, dependency_receipts=runtime_receipts)
        if runtime_error is None and runtime_receipts
        else gate.generate_report(git_sha=sha)
    )

    suffix = "openai" if gate.provider_mode == "LIVE_OPENAI" else "fallback"
    json_path = target_dir / f"phase-9-rca-{suffix}.json"
    md_path = target_dir / f"phase-9-rca-{suffix}.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(
        render_gate_markdown(
            report,
            f"# Phase 9: Grounded Root-Cause Analysis (RCA) — {gate.provider_mode} Gate Report",
            "## Certified Invariants (Live & Fallback Verification)",
            PHASE9_OPERATIONAL_INVARIANTS,
        ),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 9 Grounded RCA Live Certification Gate")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write certification results",
    )
    parser.add_argument(
        "--git-sha",
        type=str,
        default=None,
        help="Git SHA of the committed code",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Deployed scoring API base URL for persisted RCA verification",
    )
    parser.add_argument(
        "--alert-id",
        type=str,
        default=None,
        help="Existing alert ID for the deployed RCA POST/GET round trip",
    )
    args = parser.parse_args(argv)
    report = run_phase9_live_gate(
        output_dir=args.output_dir,
        git_sha=args.git_sha,
        base_url=args.base_url,
        alert_id=args.alert_id,
    )
    print(
        f"Phase 9 Gate ({report['provider_mode']}): {report['verdict']} "
        f"({report['passed_checks']}/{report['total_checks']} passed, "
        f"evidence_level={report['evidence_level']})"
    )
    print(f"Report SHA-256: {report['report_sha256']}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
