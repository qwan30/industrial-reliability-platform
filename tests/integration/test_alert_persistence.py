import os
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from tests.test_persistence import _make_decision

from industrial_reliability.alert_policy import (
    LockedAlertPolicyV1,
    compute_policy_sha256,
)
from industrial_reliability.alert_state import (
    AlertState,
    transition,
)
from industrial_reliability.persistence import (
    RuntimeStore,
)

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp")


def _make_custom_policy(**kwargs: Any) -> LockedAlertPolicyV1:
    payload: dict[str, Any] = {
        "schema_version": "alert-policy-v1",
        "source_split": "calibration",
        "source_scores_sha256": "a" * 64,
        "source_dataset_sha256": "b" * 64,
        "contract_sha256": "c" * 64,
        "model_id": "statistical",
        "model_version": "champion-statistical-v1",
        "threshold": 1.0,
        "stride_seconds": 300,
        "persistence_decisions": 1,
        "cooldown_decisions": 1,
        "merge_gap_seconds": 300,
        "calibration_false_episodes_per_day": 0.1,
        "calibration_time_in_alert": 0.01,
    }
    payload.update(kwargs)
    sha = compute_policy_sha256(payload)
    return LockedAlertPolicyV1(**payload, policy_sha256=sha)


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
    policy = _make_custom_policy()
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
    policy = _make_custom_policy()
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
    policy = _make_custom_policy(persistence_decisions=2)
    first = _make_decision(session_id, is_anomaly=True)
    second = first.model_copy(
        update={
            "decision_id": uuid4(),
            "window_id": uuid4(),
            "source_timestamp": first.source_timestamp + timedelta(minutes=5),
        }
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


@pytest.mark.integration
@pytest.mark.parametrize("decisions_before_upgrade", [2, 3])
def test_load_alert_state_replays_legacy_decisions_exactly(
    store: RuntimeStore,
    decisions_before_upgrade: int,
) -> None:
    session_id = uuid4()
    policy = _make_custom_policy(persistence_decisions=3, cooldown_decisions=2)
    first = _make_decision(session_id, is_anomaly=True)
    decisions = [first]
    for index in range(1, decisions_before_upgrade):
        decisions.append(
            first.model_copy(
                update={
                    "decision_id": uuid4(),
                    "window_id": uuid4(),
                    "source_timestamp": first.source_timestamp + timedelta(minutes=5 * index),
                }
            )
        )
    state = AlertState.empty(session_id, "metropt3")
    for decision in decisions:
        result = transition(state, decision, policy)
        store.record_decision_transition(decision, result)
        state = result.state

    with psycopg.connect(store.db_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM alert_runtime_states WHERE replay_session_id = %s",
            (str(session_id),),
        )
        connection.commit()

    recovered = store.load_alert_state(session_id, "metropt3", policy)
    assert recovered.active_alert_id == state.active_alert_id
    assert recovered.anomaly_decision_ids == state.anomaly_decision_ids
    assert recovered.anomaly_streak == state.anomaly_streak
    assert recovered.normal_streak == state.normal_streak
    assert recovered.last_decision_id == decisions[-1].decision_id
    assert store.count("alert_runtime_states", "replay_session_id", str(session_id)) == 1
