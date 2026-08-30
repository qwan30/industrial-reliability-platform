"""Unit tests for release certification validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from industrial_reliability.release_certification import (
    ReleaseCertificationValidator,
    main,
)
from industrial_reliability.report_hashes import compute_self_hash


def _write_self_hashed_report(
    path: Path, payload: dict[str, Any], hash_field: str
) -> dict[str, Any]:
    """Write a certification report with a valid embedded self-hash."""
    report = dict(payload)
    report[hash_field] = ""
    report[hash_field] = compute_self_hash(report, hash_field)
    path.write_text(json.dumps(report), encoding="utf-8")
    return report


def _write_phase1b_metrics(tmp_path: Path, verdict: str = "NOT FEASIBLE") -> None:
    models = {
        "statistical": {
            "threshold": 3500.0,
            "valid_holdout_decisions": 40000,
            "anomalous_decisions": 1000,
            "time_in_alert": 0.025,
            "pr_auc": 0.05,
            "detected_events": 3,
            "total_events": 4,
            "false_episodes": 800,
            "false_episodes_per_day": 5.7,
            "feasible": False,
            "event_results": [{"event_id": "metropt3-1", "detected": False}],
        },
        "isolation_forest": {
            "threshold": 0.62,
            "valid_holdout_decisions": 40000,
            "anomalous_decisions": 6500,
            "time_in_alert": 0.15,
            "pr_auc": 0.38,
            "detected_events": 4,
            "total_events": 4,
            "false_episodes": 1800,
            "false_episodes_per_day": 13.1,
            "feasible": False,
            "event_results": [{"event_id": "metropt3-1", "detected": True}],
        },
        "autoencoder": {
            "threshold": 0.47,
            "valid_holdout_decisions": 40000,
            "anomalous_decisions": 13000,
            "time_in_alert": 0.31,
            "pr_auc": 0.23,
            "detected_events": 4,
            "total_events": 4,
            "false_episodes": 4300,
            "false_episodes_per_day": 30.6,
            "feasible": False,
            "event_results": [{"event_id": "metropt3-1", "detected": True}],
        },
    }
    (tmp_path / "phase-1b-metrics.json").write_text(
        json.dumps(
            {
                "schema_version": "phase1b-benchmark-v1",
                "run_id": "phase1b-run-6050e71c7543",
                "timestamp": "2026-08-24T20:06:25.271753",
                "verdict": verdict,
                "selected_model": None if verdict == "NOT FEASIBLE" else "autoencoder",
                "contract_sha256": "1" * 64,
                "source_dataset_sha256": "2" * 64,
                "models": models,
            }
        ),
        encoding="utf-8",
    )


def _write_passing_phase8_report(
    tmp_path: Path,
    evidence_level: str = "INTEGRATION",
    simulated_components: list[str] | None = None,
    dependency_receipts: list[dict[str, Any]] | None = None,
) -> None:
    drills = [
        {
            "drill_type": "scoring-outage",
            "expected_classification": "SERVICE",
            "actual_classification": "SERVICE",
            "passed": True,
            "deltas": {"score_unavailable_delta": 1.0},
            "evidence_summary": "Scoring unavailable detected",
        },
        {
            "drill_type": "malformed-telemetry",
            "expected_classification": "DATA",
            "actual_classification": "DATA",
            "passed": True,
            "deltas": {"telemetry_quarantined_delta": 1.0},
            "evidence_summary": "Telemetry quarantined",
        },
        {
            "drill_type": "known-abnormal-replay",
            "expected_classification": "MACHINE",
            "actual_classification": "MACHINE",
            "passed": True,
            "deltas": {"anomaly_decisions_delta": 1.0},
            "evidence_summary": "Anomaly decision made",
        },
    ]
    _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": evidence_level,
            "simulated_components": [] if simulated_components is None else simulated_components,
            "dependency_receipts": (
                [
                    {"dependency": "kafka"},
                    {"dependency": "postgres"},
                    {"dependency": "scoring_api"},
                ]
                if dependency_receipts is None
                else dependency_receipts
            ),
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "all_passed": True,
            "drills": drills,
        },
        "self_sha256",
    )


def _write_passing_phase9_report(
    tmp_path: Path,
    evidence_level: str = "LIVE",
    provider_mode: str = "LIVE_OPENAI",
    simulated_components: list[str] | None = None,
    dependency_receipts: list[dict[str, Any]] | None = None,
) -> None:
    if provider_mode == "LIVE_OPENAI":
        checks = [
            {
                "name": "openai_sdk_responses_parse_support",
                "passed": True,
                "details": "OpenAI SDK parse support verified",
            },
            {
                "name": "allowlisted_evidence_projection",
                "passed": True,
                "details": "4 projection tools enforced",
            },
            {
                "name": "citation_enforcement_and_grounding",
                "passed": True,
                "details": "Citations valid",
            },
            {
                "name": "graceful_fallback_on_provider_error",
                "passed": True,
                "details": "Graceful fallback verified",
            },
            {
                "name": "secret_isolation_and_scrubbing",
                "passed": True,
                "details": "Secrets scrubbed",
            },
        ]
        filename = "phase-9-rca-openai.json"
        schema = "phase-9-rca-openai-v1"
        default_receipts = [{"dependency": "openai"}]
    else:
        checks = [
            {
                "name": "fallback_generator_available",
                "passed": True,
                "details": "Fallback generator operates without key",
            },
            {
                "name": "allowlisted_evidence_projection",
                "passed": True,
                "details": "4 projection tools enforced",
            },
            {
                "name": "citation_enforcement_and_grounding",
                "passed": True,
                "details": "Citations valid",
            },
            {
                "name": "secret_isolation_and_scrubbing",
                "passed": True,
                "details": "Secrets scrubbed",
            },
        ]
        filename = "phase-9-rca-fallback.json"
        schema = "phase-9-rca-fallback-v1"
        default_receipts = []

    _write_self_hashed_report(
        tmp_path / filename,
        {
            "schema_version": schema,
            "evidence_level": evidence_level,
            "provider_mode": provider_mode,
            "simulated_components": [] if simulated_components is None else simulated_components,
            "dependency_receipts": (
                default_receipts if dependency_receipts is None else dependency_receipts
            ),
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "total_checks": len(checks),
            "passed_checks": len(checks),
            "checks": checks,
        },
        "report_sha256",
    )


def test_validator_detects_infeasible_research_path(tmp_path: Path) -> None:
    # Setup mock artifacts
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    _write_passing_phase9_report(tmp_path)

    validator = ReleaseCertificationValidator(artifact_dir=tmp_path)
    report = validator.evaluate(git_sha="a" * 40)
    assert report.verdict == "NEGATIVE_RESEARCH_RELEASE"
    assert report.is_certified is True
    assert "phase1b_negative_benchmark" in report.phases_passed
    assert "phase8_observability_fault_drills" in report.phases_passed
    assert "phase9_grounded_rca" in report.phases_passed
    assert len(report.report_sha256) == 64
    assert not any("Phase 8" in lim or "Phase 9" in lim for lim in report.limitations)


def test_rejected_phase8_makes_aggregate_invalid(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase9_report(tmp_path)
    report = ReleaseCertificationValidator(tmp_path).evaluate(git_sha="a" * 40)
    assert report.verdict == "INVALID"
    assert report.is_certified is False
    assert "phase8_observability_fault_drills" not in report.phases_passed


def test_rejected_phase9_makes_aggregate_invalid(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    report = ReleaseCertificationValidator(tmp_path).evaluate(git_sha="a" * 40)
    assert report.verdict == "INVALID"
    assert report.is_certified is False
    assert "phase9_grounded_rca" not in report.phases_passed


def test_validator_rejects_failing_phase8_evidence(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "simulated_components": [],
            "dependency_receipts": [
                {"dependency": "kafka"},
                {"dependency": "postgres"},
                {"dependency": "scoring_api"},
            ],
            "git_sha": "a" * 40,
            "verdict": "FAIL",
            "all_passed": False,
            "drills": [
                {
                    "drill_type": "scoring-outage",
                    "expected_classification": "SERVICE",
                    "actual_classification": "SERVICE",
                    "passed": False,
                    "deltas": {},
                    "evidence_summary": "Failed drill",
                }
            ],
        },
        "self_sha256",
    )
    _write_passing_phase9_report(tmp_path)

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert any("Phase 8" in lim for lim in report.limitations)
    assert "phase9_grounded_rca" in report.phases_passed
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_empty_phase8_drills(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "simulated_components": [],
            "dependency_receipts": [
                {"dependency": "kafka"},
                {"dependency": "postgres"},
                {"dependency": "scoring_api"},
            ],
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "all_passed": True,
            "drills": [],
        },
        "self_sha256",
    )
    _write_passing_phase9_report(tmp_path)

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert report.is_certified is False


def test_validator_rejects_empty_phase9_checks(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-9-rca-openai.json",
        {
            "schema_version": "phase-9-rca-openai-v1",
            "evidence_level": "LIVE",
            "provider_mode": "LIVE_OPENAI",
            "simulated_components": [],
            "dependency_receipts": [{"dependency": "openai"}],
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "total_checks": 0,
            "passed_checks": 0,
            "checks": [],
        },
        "report_sha256",
    )

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase9_grounded_rca" not in report.phases_passed
    assert report.is_certified is False


def test_validator_rejects_in_process_evidence_level(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path, evidence_level="IN_PROCESS")
    _write_passing_phase9_report(tmp_path)

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert report.is_certified is False


def test_validator_rejects_fabricated_feasible_phase1b(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path, verdict="FEASIBLE")
    _write_passing_phase8_report(tmp_path)
    _write_passing_phase9_report(tmp_path)

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase1b" not in report.phases_passed
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_failing_phase9_evidence(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-9-rca-openai.json",
        {
            "schema_version": "phase-9-rca-openai-v1",
            "evidence_level": "LIVE",
            "provider_mode": "LIVE_OPENAI",
            "simulated_components": [],
            "dependency_receipts": [{"dependency": "openai"}],
            "git_sha": "a" * 40,
            "verdict": "FAIL",
            "checks": [
                {
                    "name": "openai_sdk_responses_parse_support",
                    "passed": False,
                    "details": "Failed",
                }
            ],
        },
        "report_sha256",
    )

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase9_grounded_rca" not in report.phases_passed
    assert any("Phase 9" in lim for lim in report.limitations)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_tampered_self_hash(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    report = _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "simulated_components": [],
            "dependency_receipts": [
                {"dependency": "kafka"},
                {"dependency": "postgres"},
                {"dependency": "scoring_api"},
            ],
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "all_passed": True,
            "drills": [
                {
                    "drill_type": "scoring-outage",
                    "expected_classification": "SERVICE",
                    "actual_classification": "SERVICE",
                    "passed": True,
                    "deltas": {},
                    "evidence_summary": "Passed",
                },
                {
                    "drill_type": "malformed-telemetry",
                    "expected_classification": "DATA",
                    "actual_classification": "DATA",
                    "passed": True,
                    "deltas": {},
                    "evidence_summary": "Passed",
                },
                {
                    "drill_type": "known-abnormal-replay",
                    "expected_classification": "MACHINE",
                    "actual_classification": "MACHINE",
                    "passed": True,
                    "deltas": {},
                    "evidence_summary": "Passed",
                },
            ],
        },
        "self_sha256",
    )
    report["drills"][0]["passed"] = False
    (tmp_path / "phase-8-live-fault-drills.json").write_text(json.dumps(report), encoding="utf-8")

    report_out = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report_out.phases_passed
    assert any("Phase 8" in lim for lim in report_out.limitations)
    assert report_out.verdict == "INVALID"
    assert report_out.is_certified is False


def test_validator_rejects_unit_level_evidence(tmp_path: Path) -> None:
    """A UNIT-level report renamed into the artifact dir must not certify."""
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path, evidence_level="UNIT")

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert any("Phase 8" in lim for lim in report.limitations)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_renamed_report_with_foreign_schema(tmp_path: Path) -> None:
    """A unit-gate report renamed to a release filename must not certify."""
    _write_phase1b_metrics(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-9-rca-openai.json",
        {
            "schema_version": "phase-9-rca-contract-v1",
            "evidence_level": "UNIT",
            "provider_mode": "MOCKED_CONTRACT",
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "checks": [],
        },
        "report_sha256",
    )

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase9_grounded_rca" not in report.phases_passed
    assert any("Phase 9" in lim for lim in report.limitations)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_evidence_bound_to_different_commit(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "simulated_components": [],
            "dependency_receipts": [
                {"dependency": "kafka"},
                {"dependency": "postgres"},
                {"dependency": "scoring_api"},
            ],
            "git_sha": "b" * 40,
            "verdict": "PASS",
            "all_passed": True,
            "drills": [
                {
                    "drill_type": "scoring-outage",
                    "expected_classification": "SERVICE",
                    "actual_classification": "SERVICE",
                    "passed": True,
                    "deltas": {},
                    "evidence_summary": "Passed",
                },
                {
                    "drill_type": "malformed-telemetry",
                    "expected_classification": "DATA",
                    "actual_classification": "DATA",
                    "passed": True,
                    "deltas": {},
                    "evidence_summary": "Passed",
                },
                {
                    "drill_type": "known-abnormal-replay",
                    "expected_classification": "MACHINE",
                    "actual_classification": "MACHINE",
                    "passed": True,
                    "deltas": {},
                    "evidence_summary": "Passed",
                },
            ],
        },
        "self_sha256",
    )

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert any("Phase 8" in lim for lim in report.limitations)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_current_schema_without_self_hash(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    (tmp_path / "phase-8-live-fault-drills.json").write_text(
        json.dumps(
            {
                "schema_version": "phase8-live-fault-drills-v1",
                "evidence_level": "INTEGRATION",
                "simulated_components": [],
                "dependency_receipts": [
                    {"dependency": "kafka"},
                    {"dependency": "postgres"},
                    {"dependency": "scoring_api"},
                ],
                "git_sha": "a" * 40,
                "verdict": "PASS",
            }
        ),
        encoding="utf-8",
    )

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert any("Phase 8" in lim for lim in report.limitations)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_evidence_with_simulated_components(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(
        tmp_path,
        evidence_level="INTEGRATION",
        simulated_components=["scoring API client (in-process double)"],
    )
    _write_passing_phase9_report(tmp_path)

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_phase8_missing_dependency_receipts(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(
        tmp_path,
        evidence_level="INTEGRATION",
        dependency_receipts=[{"dependency": "kafka"}],
    )
    _write_passing_phase9_report(tmp_path)

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_phase9_live_missing_openai_receipt(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    _write_passing_phase9_report(
        tmp_path,
        evidence_level="LIVE",
        provider_mode="LIVE_OPENAI",
        dependency_receipts=[],
    )

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase9_grounded_rca" not in report.phases_passed
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_unreadable_evidence(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    (tmp_path / "phase-8-live-fault-drills.json").write_text("not-json{{", encoding="utf-8")

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_handles_missing_artifact_dir(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist"
    validator = ReleaseCertificationValidator(artifact_dir=non_existent)
    report = validator.evaluate(git_sha="b" * 40)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


@pytest.mark.parametrize("invalid_sha", ["0" * 40, "abc", "G" * 40, ""])
def test_validator_fails_closed_on_invalid_git_sha(tmp_path: Path, invalid_sha: str) -> None:
    validator = ReleaseCertificationValidator(artifact_dir=tmp_path)
    report = validator.evaluate(git_sha=invalid_sha)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_run_release_certification_cli_fails_without_mandatory_evidence(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    out_file = tmp_path / "release-certification.json"
    code = main(["--artifact-dir", str(tmp_path), "--output", str(out_file), "--git-sha", "c" * 40])
    assert code == 1
    assert out_file.is_file()
    report = json.loads(out_file.read_text(encoding="utf-8"))
    assert report["verdict"] == "INVALID"
    assert report["is_certified"] is False


def test_run_release_certification_cli_passes_with_mandatory_evidence(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    _write_passing_phase9_report(tmp_path)
    out_file = tmp_path / "release-certification.json"
    code = main(["--artifact-dir", str(tmp_path), "--output", str(out_file), "--git-sha", "a" * 40])
    assert code == 0
    assert out_file.is_file()
    report = json.loads(out_file.read_text(encoding="utf-8"))
    assert report["verdict"] == "NEGATIVE_RESEARCH_RELEASE"
    assert report["is_certified"] is True
    assert report["git_sha"] == "a" * 40
    assert len(report["report_sha256"]) == 64
