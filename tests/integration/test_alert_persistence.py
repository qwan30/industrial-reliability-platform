from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from industrial_reliability.alert_policy import LockedAlertPolicyV1
from industrial_reliability.alert_state import (
    AlertState,
    transition,
)
from industrial_reliability.persistence import (
    RuntimeStore,
)
from industrial_reliability.runtime_messages import (
    EvidenceValueV1,
    ScoreDecisionV1,
)

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp")


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


def _make_decision(session_id: UUID, is_anomaly: bool = True) -> ScoreDecisionV1:
    decision_id = uuid4()
    window_id = uuid4()
    return ScoreDecisionV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="b" * 64,
        contract_sha256="c" * 64,
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        emitted_at=datetime.now(UTC),
        decision_id=decision_id,
        window_id=window_id,
        model_version="champion-statistical-v1",
        score=1.5 if is_anomaly else 0.4,
        threshold=1.0,
        is_anomaly=is_anomaly,
        evidence_vector=(
            EvidenceValueV1(
                feature_name="tp2_mean",
                feature_value=1.5,
                robust_deviation=0.5,
            ),
        ),
    )


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
