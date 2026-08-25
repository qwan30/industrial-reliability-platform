from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
import pytest

from industrial_reliability.api import create_app
from industrial_reliability.persistence import AlertDetailRecord, AlertSummaryRecord
from industrial_reliability.rca_openai import ProviderRcaDraft
from industrial_reliability.runtime_messages import RcaObservationV1, RcaReportV1


def _mock_scorer() -> Mock:
    scorer = Mock()
    scorer.model_version = "champion-statistical-v1"
    scorer.threshold = 1200.0
    scorer.feature_names = ["tp2_mean"]
    scorer.manifest = {}
    return scorer


def _fake_alert_detail(alert_id: UUID) -> AlertDetailRecord:
    session_id = uuid4()
    decision_id = uuid4()
    summary = AlertSummaryRecord(
        alert_id=alert_id,
        replay_session_id=session_id,
        machine_id="metropt3",
        state="OPEN",
        first_detection=datetime(2020, 2, 25, 0, 0),
        last_detection=datetime(2020, 2, 25, 0, 5),
        resolved_at=None,
        latest_decision_id=decision_id,
        policy_sha256="c" * 64,
    )
    events = [
        {
            "event_id": str(uuid4()),
            "alert_id": str(alert_id),
            "action": "OPENED",
            "occurred_at": "2020-02-25T00:00:00",
            "decision_ids": [str(decision_id)],
        }
    ]
    evidence = [
        {
            "evidence_id": str(uuid4()),
            "alert_id": str(alert_id),
            "decision_id": str(decision_id),
            "feature_deviations": [
                {
                    "feature_name": "tp2_mean",
                    "observed_value": 9.5,
                    "baseline_value": 8.0,
                    "absolute_deviation": 1.5,
                }
            ],
            "data_quality": {"valid_bins": 6, "observation_count": 180},
            "model": {"score": 1400.0, "threshold": 1200.0, "model_version": "champion-statistical-v1"},
            "system_health": {"queue_lag": 0, "api_status": "ok"},
        }
    ]
    decisions = [
        {
            "decision_id": str(decision_id),
            "replay_session_id": str(session_id),
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
        alert=summary,
        events=events,
        evidence=evidence,
        decisions=decisions,
        rca=None,
    )


def test_post_rca_returns_404_on_missing_alert() -> None:
    fake_store = Mock()
    fake_store.get_alert_detail.return_value = None
    app = create_app(_mock_scorer(), store=fake_store)
    client = TestClient(app)

    missing_id = uuid4()
    response = client.post(f"/v1/alerts/{missing_id}/rca")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ALERT_NOT_FOUND"


def test_post_rca_returns_unavailable_fallback_when_provider_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RCA_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RCA_OPENAI_MODEL", raising=False)

    alert_id = uuid4()
    fake_store = Mock()
    fake_store.get_alert_detail.return_value = _fake_alert_detail(alert_id)
    fake_store.get_rca.return_value = None

    app = create_app(_mock_scorer(), store=fake_store)
    client = TestClient(app)

    response = client.post(f"/v1/alerts/{alert_id}/rca")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "UNAVAILABLE"
    assert data["provider_model"] is None
    assert "persisted evidence only" in data["summary"].lower()
    assert len(data["observations"]) > 0


def test_post_rca_returns_complete_and_persists_report() -> None:
    alert_id = uuid4()
    fake_store = Mock()
    fake_store.get_alert_detail.return_value = _fake_alert_detail(alert_id)
    fake_store.get_rca.return_value = None
    fake_store.save_complete_rca.side_effect = lambda rep: rep

    fake_generator = Mock()
    fake_generator.generate.side_effect = lambda bundle: RcaReportV1(
        schema_version="rca-report-v1",
        message_id=uuid4(),
        replay_session_id=UUID(bundle.replay_session_id),
        source_dataset_sha256=bundle.source_dataset_sha256,
        contract_sha256=bundle.contract_sha256,
        source_timestamp=datetime.now(UTC).replace(tzinfo=None),
        emitted_at=datetime.now(UTC),
        report_id=f"rca-{uuid4().hex[:12]}",
        alert_id=str(alert_id),
        status="COMPLETE",
        summary="High compressor discharge pressure observed.",
        observations=(
            RcaObservationV1(
                claim="Discharge pressure elevated.",
                evidence_ids=(bundle.items[0].evidence_id,),
            ),
        ),
        uncertainty=("Anomaly evidence does not prove a mechanical root cause.",),
        next_checks=("Inspect intake check valve.",),
        evidence_ids=tuple(i.evidence_id for i in bundle.items),
        evidence_bundle_sha256=bundle.bundle_sha256,
        provider_model="gpt-4o",
    )

    app = create_app(_mock_scorer(), store=fake_store, rca_generator=fake_generator)
    client = TestClient(app)

    response = client.post(f"/v1/alerts/{alert_id}/rca")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "COMPLETE"
    assert data["provider_model"] == "gpt-4o"
    assert data["summary"] == "High compressor discharge pressure observed."
    assert fake_store.save_complete_rca.called


def test_post_rca_returns_cached_report_without_calling_generator() -> None:
    alert_id = uuid4()
    detail = _fake_alert_detail(alert_id)

    persisted_report = RcaReportV1(
        schema_version="rca-report-v1",
        message_id=uuid4(),
        replay_session_id=detail.alert.replay_session_id,
        source_dataset_sha256="0" * 64,
        contract_sha256="1" * 64,
        source_timestamp=datetime.now(UTC).replace(tzinfo=None),
        emitted_at=datetime.now(UTC),
        report_id="rca-persisted-1",
        alert_id=str(alert_id),
        status="COMPLETE",
        summary="Cached report summary.",
        observations=(
            RcaObservationV1(
                claim="Claim from cached report.",
                evidence_ids=("ev-1",),
            ),
        ),
        uncertainty=("Anomaly evidence does not prove a mechanical root cause.",),
        next_checks=(),
        evidence_ids=("ev-1", "ev-2"),
        evidence_bundle_sha256="b" * 64,
        provider_model="gpt-4o",
    )

    fake_store = Mock()
    fake_store.get_alert_detail.return_value = detail
    fake_store.get_rca.return_value = persisted_report

    fake_generator = Mock()

    app = create_app(_mock_scorer(), store=fake_store, rca_generator=fake_generator)
    client = TestClient(app)

    response = client.post(f"/v1/alerts/{alert_id}/rca")
    assert response.status_code == 200
    assert response.json()["data"]["report_id"] == "rca-persisted-1"
    assert not fake_generator.generate.called


def test_get_alert_includes_rca_field() -> None:
    alert_id = uuid4()
    detail = _fake_alert_detail(alert_id)
    rca_dict = {
        "report_id": "rca-123",
        "status": "COMPLETE",
        "summary": "Sample RCA",
    }
    detail_with_rca = AlertDetailRecord(
        alert=detail.alert,
        events=detail.events,
        evidence=detail.evidence,
        decisions=detail.decisions,
        rca=rca_dict,
    )
    fake_store = Mock()
    fake_store.get_alert_detail.return_value = detail_with_rca

    app = create_app(_mock_scorer(), store=fake_store)
    client = TestClient(app)

    response = client.get(f"/v1/alerts/{alert_id}")
    assert response.status_code == 200
    assert response.json()["data"]["rca"] == rca_dict
