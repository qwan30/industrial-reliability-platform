import os
from dataclasses import replace
from datetime import timedelta
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
    require_live = os.environ.get("REQUIRE_INTEGRATION_SERVICES", "").lower() in ("true", "1")
    try:
        store = RuntimeStore(TEST_DB_URL)
        store.check_connection()
        migration_sql_001 = Path("db/migrations/001_alert_lifecycle.sql").read_text(
            encoding="utf-8"
        )
        store.execute_script(migration_sql_001)
        migration_sql_004 = Path("db/migrations/004_alert_runtime_state.sql").read_text(
            encoding="utf-8"
        )
        store.execute_script(migration_sql_004)
        return store
    except Exception as exc:
        if require_live:
            raise RuntimeError(
                f"Required integration database unavailable at {TEST_DB_URL}: {exc}"
            ) from exc
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


@pytest.mark.integration
def test_two_anomalies_open_one_alert_across_restart(store: RuntimeStore) -> None:
    session_id = uuid4()
    policy = replace(_make_policy(), persistence_decisions=2)
    first = _make_decision(session_id, is_anomaly=True)
    second = replace(
        _make_decision(session_id, is_anomaly=True),
        decision_id=uuid4(),
        window_id=uuid4(),
        source_timestamp=first.source_timestamp + timedelta(minutes=5),
    )
    result1 = transition(AlertState.empty(session_id, "metropt3"), first, policy)
    assert result1.event is None
    store.record_decision_transition(first, result1)

    restarted = RuntimeStore(TEST_DB_URL)
    recovered = restarted.load_alert_state(session_id, "metropt3")
    assert recovered.anomaly_streak == 1
    assert recovered.anomaly_decision_ids == (first.decision_id,)

    result2 = transition(recovered, second, policy)
    assert result2.event is not None
    restarted.record_decision_transition(second, result2)
    assert restarted.count("alerts", "replay_session_id", str(session_id)) == 1
    assert restarted.count("alert_outbox") == 1
