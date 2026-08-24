from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from tests.test_persistence import _make_decision, _make_policy

from industrial_reliability.alert_state import (
    AlertState,
    transition,
)
from industrial_reliability.persistence import (
    RuntimeStore,
)

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp")


@pytest.fixture
def store() -> RuntimeStore:
    try:
        store = RuntimeStore(TEST_DB_URL)
        store.check_connection()
        migration_sql = Path("db/migrations/001_alert_lifecycle.sql").read_text(encoding="utf-8")
        store.execute_script(migration_sql)
        return store
    except Exception:
        pytest.skip("PostgreSQL unavailable at " + TEST_DB_URL)


@pytest.mark.integration
def test_record_transition_is_atomic_and_idempotent(store: RuntimeStore) -> None:
    session_id = uuid4()
    policy = _make_policy()
    decision = _make_decision(session_id, is_anomaly=True)
    state = AlertState.empty(session_id, "metropt3")

    result = transition(state, decision, policy)
    assert result.event is not None

    # First write
    store.record_decision_transition(decision, result)
    assert store.count("score_decisions", "replay_session_id", str(session_id)) == 1
    assert store.count("alerts", "replay_session_id", str(session_id)) == 1
    assert store.count("alert_events", "alert_id", str(result.event.alert_id)) == 1
    assert store.count("alert_outbox", "message_id", str(result.event.message_id)) == 1

    # Duplicate write is idempotent no-op
    store.record_decision_transition(decision, result)
    assert store.count("score_decisions", "replay_session_id", str(session_id)) == 1
    assert store.count("alert_events", "alert_id", str(result.event.alert_id)) == 1


@pytest.mark.integration
def test_load_alert_state_recovers_open_alert(store: RuntimeStore) -> None:
    session_id = uuid4()
    policy = _make_policy()
    decision = _make_decision(session_id, is_anomaly=True)
    state = AlertState.empty(session_id, "metropt3")

    result = transition(state, decision, policy)
    store.record_decision_transition(decision, result)

    # Recover state from database
    recovered_state = store.load_alert_state(session_id, "metropt3")
    assert recovered_state.active_alert_id == result.event.alert_id
    assert recovered_state.last_decision_id == decision.decision_id
