"""Shared verification checks for Phase 9 grounded RCA certification gates.

Both the contract gate (``phase9_gate``) and the dual-mode gate
(``phase9_live_gate``) verify the same invariants; this module owns the
implementations so the gates only differ in labeling and provider wiring.
All checks run against in-process doubles: they verify wiring and contracts,
never a live OpenAI call.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

from openai import OpenAI
from pydantic import ValidationError

from industrial_reliability.persistence import AlertDetailRecord, AlertSummaryRecord
from industrial_reliability.rca_evidence import (
    RCA_TOOL_NAMES,
    EvidenceBundleV1,
    EvidenceItemV1,
    gather_evidence,
)
from industrial_reliability.rca_openai import (
    OpenAiRcaGenerator,
    ProviderRcaDraft,
)
from industrial_reliability.report_hashes import (
    compute_self_hash,
    require_committed_git_sha,
)
from industrial_reliability.runtime_messages import RcaObservationV1, RcaReportV1


def check_openai_sdk_parse_support(api_key: str) -> tuple[bool, str]:
    """Verify the pinned OpenAI SDK exposes responses.parse with required parameters."""
    try:
        client = OpenAI(api_key=api_key)
        sig = inspect.signature(client.responses.parse)
        if {"model", "input", "text_format"} <= set(sig.parameters):
            return (
                True,
                "OpenAI SDK has responses.parse with required text_format parameters",
            )
        return False, "OpenAI SDK missing required parse parameters"
    except Exception as exc:
        return False, str(exc)


def gather_synthetic_alert_evidence() -> tuple[str, EvidenceBundleV1]:
    """Gather an evidence bundle for a synthetic alert from an in-process store double."""
    alert_id = uuid4()
    summary = AlertSummaryRecord(
        alert_id=alert_id,
        replay_session_id=uuid4(),
        machine_id="metropt3",
        state="OPEN",
        first_detection=datetime(2020, 2, 25, 0, 0),
        last_detection=datetime(2020, 2, 25, 0, 5),
        resolved_at=None,
        latest_decision_id=uuid4(),
        policy_sha256="c" * 64,
    )
    store = Mock()
    store.get_alert_detail.return_value = AlertDetailRecord(
        alert=summary,
        events=[],
        evidence=[],
        decisions=[],
        rca=None,
    )
    return str(alert_id), gather_evidence(str(alert_id), store)


def check_allowlisted_evidence_projection() -> tuple[bool, str]:
    """Verify the 4 allowlisted projection tools are gathered in strict order."""
    try:
        _, bundle = gather_synthetic_alert_evidence()
        tool_names = tuple(item.tool_name for item in bundle.items)
        if tool_names == RCA_TOOL_NAMES and len(bundle.bundle_sha256) == 64:
            return (
                True,
                f"4 allowlisted tools strictly gathered in order: {RCA_TOOL_NAMES}",
            )
        return False, f"Unexpected tool list: {tool_names}"
    except Exception as exc:
        return False, str(exc)


def check_citation_enforcement(provider_model: str) -> tuple[bool, str]:
    """Verify closed-world grounding: unbundled citations must be rejected."""
    try:
        ev_id = "evidence-111111111111111111111111"
        valid_payload: dict[str, Any] = {
            "schema_version": "rca-report-v1",
            "message_id": uuid4(),
            "replay_session_id": uuid4(),
            "source_dataset_sha256": "0" * 64,
            "contract_sha256": "1" * 64,
            "source_timestamp": datetime.now(UTC).replace(tzinfo=None),
            "emitted_at": datetime.now(UTC),
            "report_id": "rca-1",
            "alert_id": "alt-1",
            "status": "COMPLETE",
            "summary": "Valid summary",
            "observations": ({"claim": "Valid claim", "evidence_ids": (ev_id,)},),
            "uncertainty": ("Anomaly evidence does not prove a mechanical root cause.",),
            "next_checks": ("Check valve",),
            "evidence_ids": (ev_id,),
            "evidence_bundle_sha256": "2" * 64,
            "provider_model": provider_model,
        }
        RcaReportV1.model_validate(valid_payload)

        invalid_payload = dict(valid_payload)
        invalid_payload["observations"] = ({"claim": "Invalid", "evidence_ids": ("invented-id",)},)
        try:
            RcaReportV1.model_validate(invalid_payload)
            return (
                False,
                "Validation did not fail when observation cited non-existent evidence ID",
            )
        except ValidationError:
            return True, "Strict validation rejected non-allowlisted citations"
    except Exception as exc:
        return False, str(exc)


def check_provider_generation_and_fallback(model: str) -> tuple[bool, str]:
    """Verify complete generation and a clean UNAVAILABLE fallback on provider error."""
    try:
        bundle_test = _synthetic_provider_bundle()
        fake_client = Mock()
        fake_client.responses.parse.return_value = _grounded_provider_response()
        gen = OpenAiRcaGenerator(client=fake_client, model=model)
        comp_report = gen.generate(bundle_test)

        fake_client.responses.parse.side_effect = RuntimeError("OpenAI timeout")
        fallback_report = gen.generate(bundle_test)

        if comp_report.status == "COMPLETE" and fallback_report.status == "UNAVAILABLE":
            return (
                True,
                "Complete path produces COMPLETE report; provider errors cleanly fallback "
                "to UNAVAILABLE",
            )
        return (
            False,
            f"Unexpected status: comp={comp_report.status}, fb={fallback_report.status}",
        )
    except Exception as exc:
        return False, str(exc)


def check_graceful_fallback_on_provider_error(model: str) -> tuple[bool, str]:
    """Verify a provider outage returns an UNAVAILABLE report without crashing."""
    try:
        broken_generator = OpenAiRcaGenerator(
            client=Mock(responses=Mock(parse=Mock(side_effect=RuntimeError("Simulated timeout")))),
            model=model,
        )
        report = broken_generator.generate(_synthetic_provider_bundle())
        if report.status == "UNAVAILABLE":
            return (
                True,
                "OpenAI provider error caught and returned UNAVAILABLE report without crashing",
            )
        return False, f"Expected UNAVAILABLE report on provider error, got {report.status}"
    except Exception as exc:
        return False, str(exc)


def check_secret_isolation_from_env() -> tuple[bool, str]:
    """Verify API keys are read strictly via from_env() and scrubbed from reprs."""

    def _restore(key: str, previous: str | None) -> None:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous

    saved_key = os.environ.get("RCA_OPENAI_API_KEY")
    saved_model = os.environ.get("RCA_OPENAI_MODEL")
    os.environ["RCA_OPENAI_API_KEY"] = "sk-secret-key-gate-check"
    os.environ["RCA_OPENAI_MODEL"] = "gpt-4o"
    try:
        gen_env = OpenAiRcaGenerator.from_env()
        if gen_env is not None and "sk-secret" not in repr(gen_env):
            return (
                True,
                "API keys read strictly in from_env() and scrubbed from string representations",
            )
        return False, "API key leaked in generator representation"
    except Exception as exc:
        return False, str(exc)
    finally:
        # Restore the caller's environment verbatim so a configured live key
        # survives the contract-gate run.
        _restore("RCA_OPENAI_API_KEY", saved_key)
        _restore("RCA_OPENAI_MODEL", saved_model)


def check_secret_scrubbing_repr() -> tuple[bool, str]:
    """Verify generator string representations never contain the API key."""
    try:
        mock_client = Mock()
        mock_client.api_key = "sk-live-secret-key-12345"
        generator = OpenAiRcaGenerator(client=mock_client, model="gpt-4o-mini")
        if "sk-live-secret-key" in repr(generator):
            return False, "Secret leaked into generator repr"
        return True, "No API keys leaked in string representations"
    except Exception as exc:
        return False, str(exc)


def build_gate_report(
    *,
    git_sha: str,
    schema_version: str,
    evidence_level: str,
    provider_mode: str,
    simulated_components: Sequence[str],
    checks: list[dict[str, Any]],
    dependency_receipts: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble a self-hashed gate report dict with an explicit evidence level."""
    require_committed_git_sha(git_sha)
    all_passed = all(c["passed"] for c in checks)
    report_data: dict[str, Any] = {
        "schema_version": schema_version,
        "evidence_level": evidence_level,
        "provider_mode": provider_mode,
        "simulated_components": list(simulated_components),
        "dependency_receipts": list(dependency_receipts or []),
        "git_sha": git_sha,
        "certified_at": datetime.now(UTC).isoformat(),
        "verdict": "PASS" if all_passed else "FAIL",
        "checks": checks,
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["passed"]),
        "failed_checks": sum(1 for c in checks if not c["passed"]),
        "report_sha256": "",
    }
    report_data["report_sha256"] = compute_self_hash(report_data, "report_sha256")
    return report_data


def render_gate_markdown(
    report: Mapping[str, Any],
    title: str,
    invariants_heading: str,
    invariants: Sequence[str],
) -> str:
    """Render a gate report dict as a Markdown document."""
    md_lines = [
        title,
        "",
        f"- **Verdict:** `{report['verdict']}`",
        f"- **Evidence Level:** `{report['evidence_level']}`",
        f"- **Provider Mode:** `{report['provider_mode']}`",
        f"- **Simulated Components:** `{', '.join(report['simulated_components'])}`",
        f"- **Git SHA:** `{report['git_sha']}`",
        f"- **Certified At:** `{report['certified_at']}`",
        f"- **Report SHA-256:** `{report['report_sha256']}`",
        f"- **Passed Checks:** `{report['passed_checks']} / {report['total_checks']}`",
        "",
        invariants_heading,
        "",
        "| Check Name | Status | Details |",
        "| :--- | :--- | :--- |",
    ]
    for chk in report["checks"]:
        status_sym = "PASS" if chk["passed"] else "FAIL"
        md_lines.append(f"| `{chk['name']}` | **{status_sym}** | {chk['details']} |")
    md_lines.append("")
    md_lines.extend(f"- {inv}" for inv in invariants)
    return "\n".join(md_lines) + "\n"


def _synthetic_provider_bundle() -> EvidenceBundleV1:
    item = EvidenceItemV1(
        evidence_id="evidence-111111111111111111111111",
        tool_name="get_alert",
        observed_at=datetime.now(UTC),
        facts={"alert_id": "alt-1"},
    )
    return EvidenceBundleV1(
        schema_version="rca-evidence-bundle-v1",
        alert_id="alt-1",
        replay_session_id="rep-1",
        model_version="champion-v1",
        contract_sha256="0" * 64,
        source_dataset_sha256="1" * 64,
        items=(item,),
        bundle_sha256="2" * 64,
    )


def _grounded_provider_response() -> Mock:
    fake_resp = Mock()
    fake_resp.output_parsed = ProviderRcaDraft(
        summary="Grounded test summary",
        observations=(
            RcaObservationV1(
                claim="Grounded observation",
                evidence_ids=("evidence-111111111111111111111111",),
            ),
        ),
        uncertainty=("Anomaly evidence does not prove a mechanical root cause.",),
        next_checks=("Inspect unit.",),
    )
    return fake_resp
