from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from industrial_reliability.persistence import AlertDetailRecord, AlertSummaryRecord
from industrial_reliability.rca_evidence import (
    RCA_TOOL_NAMES,
    AlertNotFound,
    gather_evidence,
)


def _fake_alert_detail() -> AlertDetailRecord:
    alert_id = "a1b2c3d4-0000-0000-0000-000000000001"
    session_id = "b1b2c3d4-0000-0000-0000-000000000001"
    decision_id = "d1b2c3d4-0000-0000-0000-000000000001"

    alert_summary = AlertSummaryRecord(
        alert_id=UUID(alert_id),
        replay_session_id=UUID(session_id),
        machine_id="metropt3",
        state="OPEN",
        first_detection=datetime(2020, 2, 25, 0, 0),
        last_detection=datetime(2020, 2, 25, 0, 5),
        resolved_at=None,
        latest_decision_id=UUID(decision_id),
        policy_sha256="c" * 64,
    )
    events = [
        {
            "event_id": str(uuid4()),
            "alert_id": alert_id,
            "action": "OPENED",
            "occurred_at": "2020-02-25T00:00:00",
            "decision_ids": [decision_id],
        }
    ]
    evidence = [
        {
            "evidence_id": str(uuid4()),
            "alert_id": alert_id,
            "decision_id": decision_id,
            "feature_deviations": [
                {
                    "feature_name": "tp2_mean",
                    "observed_value": 9.5,
                    "baseline_value": 8.0,
                    "absolute_deviation": 1.5,
                }
            ],
            "data_quality": {"valid_bins": 6, "observation_count": 180},
            "model": {
                "score": 1400.0,
                "threshold": 1200.0,
                "model_version": "champion-statistical-v1",
            },
            "system_health": {"queue_lag": 0, "api_status": "ok"},
        }
    ]
    decisions = [
        {
            "decision_id": decision_id,
            "replay_session_id": session_id,
            "source_dataset_sha256": "0" * 64,
            "contract_sha256": "1" * 64,
            "source_timestamp": "2020-02-25T00:05:00",
            "score": 1400.0,
            "threshold": 1200.0,
            "is_anomaly": True,
            "model_version": "champion-statistical-v1",
        }
    ]
    return AlertDetailRecord(
        alert=alert_summary,
        events=events,
        evidence=evidence,
        decisions=decisions,
        rca=None,
    )


def test_gather_evidence_calls_only_fixed_tools() -> None:
    fake_store = Mock()
    fake_store.get_alert_detail.return_value = _fake_alert_detail()

    bundle = gather_evidence("a1b2c3d4-0000-0000-0000-000000000001", fake_store)
    assert tuple(item.tool_name for item in bundle.items) == RCA_TOOL_NAMES
    assert bundle.alert_id == "a1b2c3d4-0000-0000-0000-000000000001"
    assert len(bundle.bundle_sha256) == 64
    assert len(bundle.items) == 4
    for item in bundle.items:
        assert item.evidence_id.startswith("evidence-")
        assert len(item.evidence_id) == len("evidence-") + 24


def test_bundle_is_deterministic_and_contains_no_raw_telemetry() -> None:
    fake_store = Mock()
    fake_store.get_alert_detail.return_value = _fake_alert_detail()

    first = gather_evidence("a1b2c3d4-0000-0000-0000-000000000001", fake_store)
    second = gather_evidence("a1b2c3d4-0000-0000-0000-000000000001", fake_store)
    assert first == second
    assert first.bundle_sha256 == second.bundle_sha256

    encoded = first.model_dump_json()
    assert "raw_telemetry" not in encoded
    assert "DATABASE_URL" not in encoded
    assert "api_key" not in encoded.lower()
    assert "password" not in encoded.lower()


def test_unknown_alert_fails_before_provider_call() -> None:
    fake_store = Mock()
    fake_store.get_alert_detail.return_value = None

    with pytest.raises(AlertNotFound, match="missing-alert"):
        gather_evidence("missing-alert", fake_store)


def test_sanitize_scalar_rejects_non_finite() -> None:
    from industrial_reliability.rca_evidence import _sanitize_scalar

    assert _sanitize_scalar(10) == 10
    assert _sanitize_scalar(3.14) == 3.14
    assert _sanitize_scalar(True) is True
    assert _sanitize_scalar(["a", "b"]) == ["a", "b"]
    with pytest.raises(ValueError, match="Non-finite float"):
        _sanitize_scalar(float("nan"))
    with pytest.raises(ValueError, match="Non-finite float"):
        _sanitize_scalar(float("inf"))


def test_gather_evidence_with_empty_events_and_evidence(tmp_path: Path) -> None:
    alert_summary = AlertSummaryRecord(
        alert_id=uuid4(),
        replay_session_id=uuid4(),
        machine_id="metropt3",
        state="RESOLVED",
        first_detection=datetime(2020, 2, 25, 0, 0, tzinfo=UTC),
        last_detection=datetime(2020, 2, 25, 0, 10, tzinfo=UTC),
        resolved_at=datetime(2020, 2, 25, 0, 10, tzinfo=UTC),
        latest_decision_id=uuid4(),
        policy_sha256="c" * 64,
    )
    detail = AlertDetailRecord(
        alert=alert_summary,
        events=[],
        evidence=[],
        decisions=[],
        rca=None,
    )
    fake_store = Mock()
    fake_store.get_alert_detail.return_value = detail

    bundle = gather_evidence(str(alert_summary.alert_id), fake_store, champion_dir=tmp_path)
    assert len(bundle.items) == 4
    assert bundle.alert_id == str(alert_summary.alert_id)
