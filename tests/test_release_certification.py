"""Unit tests for release certification validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from industrial_reliability.release_certification import (
    ReleaseCertificationValidator,
    main,
)


def test_validator_detects_infeasible_research_path(tmp_path: Path) -> None:
    # Setup mock artifacts
    (tmp_path / "phase-1b-metrics.json").write_text(
        json.dumps(
            {
                "schema_version": "phase1b-benchmark-v1",
                "verdict": "NOT FEASIBLE",
                "selected_model": None,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "phase-8-in-process-fault-drills.json").write_text(
        json.dumps({"schema_version": "phase8-in-process-fault-drills-v1", "all_passed": True}),
        encoding="utf-8",
    )
    (tmp_path / "phase-9-rca-fallback.json").write_text(
        json.dumps({"schema_version": "phase-9-rca-fallback-v1", "verdict": "PASS"}),
        encoding="utf-8",
    )

    validator = ReleaseCertificationValidator(artifact_dir=tmp_path)
    report = validator.evaluate(git_sha="a" * 40)
    assert report.verdict == "NEGATIVE_RESEARCH_RELEASE"
    assert report.is_certified is True
    assert "phase1b_negative_benchmark" in report.phases_passed
    assert "phase8_observability_fault_drills" in report.phases_passed
    assert "phase9_grounded_rca" in report.phases_passed
    assert len(report.report_sha256) == 64


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


def test_run_release_certification_cli(tmp_path: Path) -> None:
    (tmp_path / "phase-1b-metrics.json").write_text(
        json.dumps({"verdict": "NOT FEASIBLE"}), encoding="utf-8"
    )
    out_file = tmp_path / "release-certification.json"
    code = main(["--artifact-dir", str(tmp_path), "--output", str(out_file), "--git-sha", "c" * 40])
    assert code == 0
    assert out_file.is_file()
    assert (tmp_path / "release-certification.md").is_file()
