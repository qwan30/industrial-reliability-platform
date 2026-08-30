from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from industrial_reliability.alert_policy import (
    LockedAlertPolicyV1,
    compute_policy_sha256,
)
from industrial_reliability.alert_state import (
    AlertState,
    transition,
)
from industrial_reliability.console_stream import ConsoleEventV1
from industrial_reliability.persistence import (
    RuntimeStore,
    _state_from_payload,
    _state_payload,
)
from industrial_reliability.runtime_messages import (
    EvidenceValueV1,
    ReplayStatusV1,
    ScoreDecisionV1,
)


def _make_policy() -> LockedAlertPolicyV1:
    payload = {
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
    sha = compute_policy_sha256(payload)
    return LockedAlertPolicyV1(**payload, policy_sha256=sha)


def _make_decision(
    session_id: UUID,
    is_anomaly: bool = True,
    contract_sha256: str = "c" * 64,
) -> ScoreDecisionV1:
    decision_id = uuid4()
    window_id = uuid4()
    return ScoreDecisionV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="b" * 64,
        contract_sha256=contract_sha256,
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


def test_store_record_replay_status() -> None:
    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    status = ReplayStatusV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        state="COMPLETED",
        last_sequence=100,
    )

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("psycopg.connect", return_value=mock_conn):
        store.record_replay_status(status)
        assert mock_cur.execute.called
        assert mock_conn.commit.called


def test_store_record_decision_transition() -> None:
    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    session_id = uuid4()
    policy = _make_policy()
    decision = _make_decision(session_id, is_anomaly=True)
    state = AlertState.empty(session_id, "metropt3")
    res = transition(state, decision, policy)

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("psycopg.connect", return_value=mock_conn):
        store.record_decision_transition(decision, res)
        assert mock_cur.execute.call_count >= 4
        assert mock_conn.commit.called


def test_state_payload_and_from_payload_roundtrip() -> None:
    session_id = uuid4()
    alert_id = uuid4()
    prev_alert_id = uuid4()
    d1 = uuid4()
    d2 = uuid4()
    now = datetime(2026, 8, 30, 10, 0, 0)
    state = AlertState(
        replay_session_id=session_id,
        machine_id="metropt3",
        active_alert_id=alert_id,
        previous_alert_id=prev_alert_id,
        first_detection=now,
        last_detection=now,
        resolved_at=None,
        anomaly_decision_ids=(d1, d2),
        anomaly_streak=2,
        normal_streak=0,
        last_decision_id=d2,
        last_source_timestamp=now,
    )
    payload = _state_payload(state)
    assert payload["replay_session_id"] == str(session_id)
    assert payload["active_alert_id"] == str(alert_id)
    assert payload["previous_alert_id"] == str(prev_alert_id)
    assert payload["first_detection"] == now.isoformat()
    assert payload["last_detection"] == now.isoformat()
    assert payload["resolved_at"] is None
    assert payload["anomaly_decision_ids"] == [str(d1), str(d2)]
    assert payload["anomaly_streak"] == 2
    assert payload["normal_streak"] == 0
    assert payload["last_decision_id"] == str(d2)
    assert payload["last_source_timestamp"] == now.isoformat()

    recovered = _state_from_payload(payload)
    assert recovered == state

    # Test empty / None fields round-trip
    empty_state = AlertState.empty(session_id, "metropt3")
    empty_payload = _state_payload(empty_state)
    recovered_empty = _state_from_payload(empty_payload)
    assert recovered_empty == empty_state


def test_store_load_alert_state_found() -> None:
    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    session_id = uuid4()
    state = AlertState(
        replay_session_id=session_id,
        machine_id="metropt3",
        active_alert_id=None,
        previous_alert_id=None,
        first_detection=None,
        last_detection=None,
        resolved_at=None,
        anomaly_decision_ids=(uuid4(),),
        anomaly_streak=1,
        normal_streak=0,
        last_decision_id=uuid4(),
        last_source_timestamp=datetime(2026, 8, 30, 10, 0, 0),
    )
    payload = _state_payload(state)

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = {"payload": payload}

    with patch("psycopg.connect", return_value=mock_conn):
        loaded = store.load_alert_state(session_id, "metropt3")
        assert loaded == state
        # Verify SQL queries alert_runtime_states
        query = mock_cur.execute.call_args[0][0]
        assert "alert_runtime_states" in query

        # Also test if row["payload"] is a serialized json string
        import json

        mock_cur.fetchone.return_value = {"payload": json.dumps(payload)}
        loaded_from_json_str = store.load_alert_state(session_id, "metropt3")
        assert loaded_from_json_str == state


def test_store_record_decision_transition_upserts_runtime_state_when_no_event() -> None:
    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    session_id = uuid4()
    policy = _make_policy()
    # persistence_decisions is 2, so 1st anomaly emits no event
    from dataclasses import replace

    policy = replace(policy, persistence_decisions=2)
    decision = _make_decision(session_id, is_anomaly=True)
    state = AlertState.empty(session_id, "metropt3")
    res = transition(state, decision, policy)
    assert res.event is None
    assert res.state.anomaly_streak == 1

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("psycopg.connect", return_value=mock_conn):
        store.record_decision_transition(decision, res)
        # Check all SQL executed
        queries = [call[0][0] for call in mock_cur.execute.call_args_list]
        assert any("INSERT INTO alert_runtime_states" in q for q in queries)
        assert mock_conn.commit.called


def test_store_load_alert_state_empty() -> None:
    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    session_id = uuid4()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None

    with patch("psycopg.connect", return_value=mock_conn):
        state = store.load_alert_state(session_id, "metropt3")
        assert state.active_alert_id is None
        assert state.replay_session_id == session_id
        assert state.anomaly_streak == 0
        # Verify SQL queries alert_runtime_states
        query = mock_cur.execute.call_args[0][0]
        assert "alert_runtime_states" in query


def test_store_outbox_operations() -> None:
    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    msg_id = uuid4()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = {
        "message_id": str(msg_id),
        "topic": "irp.alerts.v1",
        "message_key": "metropt3",
        "payload": {"action": "OPENED"},
    }

    with patch("psycopg.connect", return_value=mock_conn):
        row = store.next_unpublished_outbox()
        assert row is not None
        assert row.message_id == msg_id
        assert row.topic == "irp.alerts.v1"

        store.mark_outbox_published(msg_id)
        assert mock_cur.execute.called


def test_store_read_apis() -> None:
    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    session_id = uuid4()
    alert_id = uuid4()
    dec_id = uuid4()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # 1. get_replay
    mock_cur.fetchone.return_value = {
        "replay_session_id": str(session_id),
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "model_version": "champion-statistical-v1",
        "state": "COMPLETED",
        "last_sequence": 100,
        "source_timestamp": datetime(2020, 3, 1, 0, 0),
        "error_code": None,
        "updated_at": datetime.now(UTC),
    }

    with patch("psycopg.connect", return_value=mock_conn):
        replay = store.get_replay(session_id)
        assert replay is not None
        assert replay.replay_session_id == session_id

    # 2. list_alerts
    mock_cur.fetchall.return_value = [
        {
            "alert_id": str(alert_id),
            "replay_session_id": str(session_id),
            "machine_id": "metropt3",
            "state": "OPEN",
            "first_detection": datetime(2020, 4, 18, 0, 0),
            "last_detection": datetime(2020, 4, 18, 0, 5),
            "resolved_at": None,
            "latest_decision_id": str(dec_id),
            "policy_sha256": "d" * 64,
        }
    ]
    with patch("psycopg.connect", return_value=mock_conn):
        alerts = store.list_alerts(session_id)
        assert len(alerts) == 1
        assert alerts[0].alert_id == alert_id

    # 3. count
    mock_cur.fetchone.return_value = (5,)
    with patch("psycopg.connect", return_value=mock_conn):
        cnt = store.count("alerts", "replay_session_id", str(session_id))
        assert cnt == 5

    # 4. Invalid count table
    with pytest.raises(ValueError, match="Invalid table"):
        store.count("invalid_table")


def test_count_active_alerts() -> None:
    store = RuntimeStore("postgresql://test")
    with patch("industrial_reliability.persistence.psycopg.connect") as connect:
        connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = {
            "count": 2
        }
        assert store.count_active_alerts() == 2


def test_store_get_alert_detail() -> None:

    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    session_id = uuid4()
    alert_id = uuid4()
    dec_id = uuid4()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    mock_cur.fetchone.return_value = {
        "alert_id": str(alert_id),
        "replay_session_id": str(session_id),
        "machine_id": "metropt3",
        "state": "OPEN",
        "first_detection": datetime(2020, 4, 18, 0, 0),
        "last_detection": datetime(2020, 4, 18, 0, 5),
        "resolved_at": None,
        "latest_decision_id": str(dec_id),
        "policy_sha256": "d" * 64,
    }
    mock_cur.fetchall.side_effect = [
        [{"payload": {"action": "OPENED"}}],
        [{"payload": {"evidence_id": str(uuid4())}}],
        [{"payload": {"decision_id": str(dec_id)}}],
    ]

    with patch("psycopg.connect", return_value=mock_conn):
        detail = store.get_alert_detail(alert_id)
        assert detail is not None
        assert detail.alert.alert_id == alert_id
        assert len(detail.events) == 1
        assert len(detail.evidence) == 1
        assert len(detail.decisions) == 1

        # Missing alert
        mock_cur.fetchone.return_value = None
        assert store.get_alert_detail(uuid4()) is None


def test_store_append_and_query_console_events() -> None:
    store = RuntimeStore("postgresql://test:5432/test")
    session_id = uuid4()
    event = ConsoleEventV1(
        event_id="ev-1",
        replay_session_id=str(session_id),
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        payload={"score": 1.5},
        durable=True,
    )

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("psycopg.connect", return_value=mock_conn):
        store.append_console_event(event)
        assert mock_cur.execute.called

        # Query events_after with None
        mock_cur.fetchall.return_value = [
            {
                "event_id": "ev-1",
                "replay_session_id": str(session_id),
                "event_type": "score",
                "source_timestamp": datetime(2020, 4, 18, 0, 5),
                "payload": {"score": 1.5},
            }
        ]
        events = store.events_after(str(session_id), after_event_id=None)
        assert len(events) == 1
        assert events[0].event_id == "ev-1"

        # Query events_after with after_event_id
        mock_cur.fetchone.return_value = {"stream_sequence": 1}
        events2 = store.events_after(str(session_id), after_event_id="ev-1")
        assert len(events2) == 1

        # Unknown after_event_id
        mock_cur.fetchone.return_value = None
        events_unknown = store.events_after(str(session_id), after_event_id="ev-unknown")
        assert events_unknown == ()
