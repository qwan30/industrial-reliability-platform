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
    (tmp_path / "phase-1b-metrics.json").write_text(
        json.dumps(
            {
                "schema_version": "phase1b-benchmark-v1",
                "verdict": verdict,
                "selected_model": None,
            }
        ),
        encoding="utf-8",
    )


def _write_passing_phase8_report(tmp_path: Path) -> None:
    _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "drills": [],
        },
        "self_sha256",
    )


def _write_passing_phase9_report(tmp_path: Path) -> None:
    _write_self_hashed_report(
        tmp_path / "phase-9-rca-fallback.json",
        {
            "schema_version": "phase-9-rca-fallback-v1",
            "evidence_level": "INTEGRATION",
            "provider_mode": "FALLBACK_ONLY",
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "checks": [],
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
            "git_sha": "a" * 40,
            "verdict": "FAIL",
            "drills": [],
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


def test_validator_rejects_failing_phase9_evidence(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-9-rca-fallback.json",
        {
            "schema_version": "phase-9-rca-fallback-v1",
            "evidence_level": "INTEGRATION",
            "provider_mode": "FALLBACK_ONLY",
            "git_sha": "a" * 40,
            "verdict": "FAIL",
            "checks": [],
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
    # Write a passing report, then mutate its payload without recomputing the
    # embedded self-hash (tamper simulation).
    report = _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "drills": [],
        },
        "self_sha256",
    )
    report["drills"] = [{"drill_type": "scoring-outage", "passed": False}]
    (tmp_path / "phase-8-live-fault-drills.json").write_text(
        json.dumps(report), encoding="utf-8"
    )

    report_out = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report_out.phases_passed
    assert any("Phase 8" in lim for lim in report_out.limitations)
    assert report_out.verdict == "INVALID"
    assert report_out.is_certified is False


def test_validator_rejects_unit_level_evidence(tmp_path: Path) -> None:
    """A UNIT-level report renamed into the artifact dir must not certify."""
    _write_phase1b_metrics(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "UNIT",
            "git_sha": "a" * 40,
            "verdict": "PASS",
            "drills": [],
        },
        "self_sha256",
    )

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert any("Phase 8" in lim for lim in report.limitations)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_validator_rejects_renamed_report_with_foreign_schema(tmp_path: Path) -> None:
    """A unit-gate report renamed to a release filename must not certify."""
    _write_phase1b_metrics(tmp_path)
    # phase-9 contract gate report (UNIT evidence, MOCKED_CONTRACT) renamed to
    # the fallback filename inspected by release certification.
    _write_self_hashed_report(
        tmp_path / "phase-9-rca-fallback.json",
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
    # Passing, self-consistent report produced for a DIFFERENT commit.
    _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "git_sha": "b" * 40,
            "verdict": "PASS",
            "drills": [],
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
        json.dumps({
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "git_sha": "a" * 40,
            "verdict": "PASS",
        }),
        encoding="utf-8",
    )

    report = ReleaseCertificationValidator(artifact_dir=tmp_path).evaluate(git_sha="a" * 40)
    assert "phase8_observability_fault_drills" not in report.phases_passed
    assert any("Phase 8" in lim for lim in report.limitations)
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
    (tmp_path / "phase-1b-metrics.json").write_text(
        json.dumps({
            "schema_version": "phase1b-benchmark-v1",
            "verdict": "NOT FEASIBLE",
        }),
        encoding="utf-8",
    )
    out_file = tmp_path / "release-certification.json"
    code = main(["--artifact-dir", str(tmp_path), "--output", str(out_file), "--git-sha", "c" * 40])
    assert code == 1
    assert out_file.is_file()
    report = json.loads(out_file.read_text(encoding="utf-8"))
    assert report["verdict"] == "INVALID"
    assert report["is_certified"] is False


def test_run_release_certification_cli_passes_with_mandatory_evidence(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_self_hashed_report(
        tmp_path / "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-drills-v1",
            "evidence_level": "INTEGRATION",
            "git_sha": "c" * 40,
            "verdict": "PASS",
            "drills": [],
        },
        "self_sha256",
    )
    _write_self_hashed_report(
        tmp_path / "phase-9-rca-fallback.json",
        {
            "schema_version": "phase-9-rca-fallback-v1",
            "evidence_level": "INTEGRATION",
            "provider_mode": "FALLBACK_ONLY",
            "git_sha": "c" * 40,
            "verdict": "PASS",
            "checks": [],
        },
        "report_sha256",
    )
    out_file = tmp_path / "release-certification.json"
    code = main(["--artifact-dir", str(tmp_path), "--output", str(out_file), "--git-sha", "c" * 40])
    assert code == 0
    assert out_file.is_file()
    report = json.loads(out_file.read_text(encoding="utf-8"))
    assert report["verdict"] == "NEGATIVE_RESEARCH_RELEASE"
    assert report["is_certified"] is True
    assert report["git_sha"] == "c" * 40
    assert len(report["report_sha256"]) == 64

