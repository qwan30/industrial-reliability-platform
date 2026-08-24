from __future__ import annotations

import json
from pathlib import Path

import pytest

from industrial_reliability.alert_policy import LockedAlertPolicyV1
from industrial_reliability.phase5_gate import Phase5Evidence, write_gate


def _make_policy() -> LockedAlertPolicyV1:
    return LockedAlertPolicyV1(
        schema_version="alert-policy-v1",
        source_split="calibration",
        source_scores_sha256="a" * 64,
        source_dataset_sha256="b" * 64,
        contract_sha256="c" * 64,
        model_id="statistical",
        model_version="champion-statistical-v1",
        threshold=1.0,
        stride_seconds=300,
        persistence_decisions=1,
        cooldown_decisions=1,
        merge_gap_seconds=300,
        calibration_false_episodes_per_day=0.1,
        calibration_time_in_alert=0.01,
        policy_sha256="d" * 64,
    )


def test_phase5_gate_writing(tmp_path: Path) -> None:
    evidence = Phase5Evidence(
        policy_locked_before_holdout=True,
        duplicate_idempotence_passed=True,
        restart_recovery_passed=True,
        traceability_passed=True,
        code_git_sha="0b8edcd" * 5,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        model_version="champion-statistical-v1",
        policy_sha256="c" * 64,
    )
    out_file = tmp_path / "phase5-gate.json"
    write_gate(out_file, evidence)
    assert out_file.is_file()

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["policy_locked_before_holdout"] is True
    assert "gate_sha256" in data


def test_phase5_gate_fails_on_incomplete_evidence(tmp_path: Path) -> None:
    evidence = Phase5Evidence(
        policy_locked_before_holdout=False,  # Failed!
        duplicate_idempotence_passed=True,
        restart_recovery_passed=True,
        traceability_passed=True,
        code_git_sha="0b8edcd" * 5,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        model_version="champion-statistical-v1",
        policy_sha256="c" * 64,
    )
    out_file = tmp_path / "phase5-gate.json"
    with pytest.raises(ValueError, match="gate verification failed"):
        write_gate(out_file, evidence)
