from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from tests.test_persistence import _make_decision, _make_policy

from industrial_reliability.alert_state import AlertState, transition
from industrial_reliability.persistence import RuntimeStore
from industrial_reliability.runtime_messages import RcaObservationV1, RcaReportV1

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp")


@pytest.fixture
def store() -> RuntimeStore:
    try:
        store = RuntimeStore(TEST_DB_URL)
        store.check_connection()
        m1 = Path("db/migrations/001_alert_lifecycle.sql").read_text(encoding="utf-8")
        store.execute_script(m1)
        m3 = Path("db/migrations/003_rca_reports.sql").read_text(encoding="utf-8")
        store.execute_script(m3)
        return store
    except Exception:
        pytest.skip("PostgreSQL unavailable at " + TEST_DB_URL)


@pytest.mark.integration
def test_rca_report_persistence_and_idempotency(store: RuntimeStore) -> None:
    session_id = uuid4()
    policy = _make_policy()
    decision = _make_decision(session_id, is_anomaly=True)
    state = AlertState.empty(session_id, "metropt3")
    result = transition(state, decision, policy)

    store.record_decision_transition(decision, result)
    alert_id = result.event.alert_id  # type: ignore[union-attr]

    report = RcaReportV1(
        schema_version="rca-report-v1",
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="0" * 64,
        contract_sha256="1" * 64,
        source_timestamp=datetime.now(UTC).replace(tzinfo=None),
        emitted_at=datetime.now(UTC),
        report_id=f"rca-{uuid4().hex[:12]}",
        alert_id=str(alert_id),
        status="COMPLETE",
        summary="Test RCA complete summary.",
        observations=(
            RcaObservationV1(
                claim="Pressure spike observed during cycle.",
                evidence_ids=("ev-1",),
            ),
        ),
        uncertainty=("Anomaly evidence does not prove a mechanical root cause.",),
        next_checks=("Inspect intake valve.",),
        evidence_ids=("ev-1", "ev-2"),
        evidence_bundle_sha256="e" * 64,
        provider_model="gpt-4o",
    )

    # First write
    saved = store.save_complete_rca(report)
    assert saved.report_id == report.report_id
    assert store.count("rca_reports", "alert_id", str(alert_id)) == 1

    # Second write with same alert_id and bundle_sha256 is idempotent
    saved_second = store.save_complete_rca(report)
    assert saved_second.report_id == report.report_id
    assert store.count("rca_reports", "alert_id", str(alert_id)) == 1

    # Query via get_rca
    loaded = store.get_rca(alert_id)
    assert loaded is not None
    assert loaded.report_id == report.report_id
    assert loaded.status == "COMPLETE"
    assert loaded.summary == "Test RCA complete summary."

    # get_alert_detail includes rca
    detail = store.get_alert_detail(alert_id)
    assert detail is not None
    assert detail.rca is not None
    assert detail.rca["report_id"] == report.report_id
