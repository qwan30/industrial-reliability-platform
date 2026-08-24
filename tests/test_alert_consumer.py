from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from industrial_reliability.alert_consumer import (
    AlertConsumer,
    AlertOutboxDispatcher,
    ProcessOutcome,
)
from industrial_reliability.alert_policy import LockedAlertPolicyV1
from industrial_reliability.alert_state import AlertState
from industrial_reliability.kafka_io import encode_message
from industrial_reliability.persistence import OutboxRow, RuntimeStore
from industrial_reliability.runtime_messages import (
    EvidenceValueV1,
    ScoreDecisionV1,
)


class MockKafkaRecord:
    def __init__(self, value: bytes, topic: str = "irp.scores.v1", offset: int = 0) -> None:
        self.value = value
        self.topic = topic
        self.offset = offset


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


def _make_decision(
    session_id: UUID,
    is_anomaly: bool = True,
    contract_sha256: str = "c" * 64,
) -> ScoreDecisionV1:
    return ScoreDecisionV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="b" * 64,
        contract_sha256=contract_sha256,
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        emitted_at=datetime.now(UTC),
        decision_id=uuid4(),
        window_id=uuid4(),
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


@pytest.mark.asyncio
async def test_alert_consumer_commits_after_successful_persistence() -> None:
    policy = _make_policy()
    session_id = uuid4()
    mock_store = MagicMock(spec=RuntimeStore)
    mock_store.load_alert_state.return_value = AlertState.empty(session_id, "metropt3")
    consumer = AlertConsumer(store=mock_store, policy=policy)

    decision = _make_decision(session_id)
    record = MockKafkaRecord(encode_message(decision))

    outcome = await consumer.process(record)
    assert outcome == ProcessOutcome.COMMITTED
    assert mock_store.load_alert_state.called
    assert mock_store.record_decision_transition.called


@pytest.mark.asyncio
async def test_contract_mismatch_fails_session_closed() -> None:
    policy = _make_policy()
    mock_store = MagicMock(spec=RuntimeStore)
    mock_producer = AsyncMock()
    consumer = AlertConsumer(store=mock_store, policy=policy, producer=mock_producer)

    session_id = uuid4()
    decision = _make_decision(session_id, contract_sha256="f" * 64)  # Mismatch!
    record = MockKafkaRecord(encode_message(decision))

    outcome = await consumer.process(record)
    assert outcome == ProcessOutcome.SESSION_FAILED
    assert mock_producer.send_and_wait.called


@pytest.mark.asyncio
async def test_outbox_dispatcher_publishes_and_marks_completed() -> None:
    mock_store = MagicMock(spec=RuntimeStore)
    msg_id = uuid4()
    mock_store.next_unpublished_outbox.side_effect = [
        OutboxRow(
            message_id=msg_id,
            topic="irp.alerts.v1",
            message_key="metropt3",
            payload={"action": "OPENED"},
        ),
        None,
    ]

    mock_producer = AsyncMock()
    dispatcher = AlertOutboxDispatcher(store=mock_store, producer=mock_producer)

    dispatched = await dispatcher.dispatch_one()
    assert dispatched is True
    assert mock_producer.send_and_wait.called
    mock_store.mark_outbox_published.assert_called_once_with(msg_id)

    # Empty outbox
    dispatched_empty = await dispatcher.dispatch_one()
    assert dispatched_empty is False


@pytest.mark.asyncio
async def test_alert_consumer_decode_error_and_skipped() -> None:
    policy = _make_policy()
    mock_store = MagicMock(spec=RuntimeStore)
    consumer = AlertConsumer(store=mock_store, policy=policy)

    # 1. Invalid payload
    bad_record = MockKafkaRecord(b"not_valid_json")
    outcome = await consumer.process(bad_record)
    assert outcome == ProcessOutcome.QUARANTINED

    # 2. Skipped failed session
    session_id = uuid4()
    consumer._failed_sessions.add(session_id)
    dec = _make_decision(session_id)
    outcome_skipped = await consumer.process(MockKafkaRecord(encode_message(dec)))
    assert outcome_skipped == ProcessOutcome.SKIPPED


@pytest.mark.asyncio
async def test_outbox_dispatcher_run_loop() -> None:
    mock_store = MagicMock(spec=RuntimeStore)
    mock_store.next_unpublished_outbox.return_value = None
    mock_producer = AsyncMock()
    dispatcher = AlertOutboxDispatcher(store=mock_store, producer=mock_producer)

    loop_task = asyncio.create_task(dispatcher.run_loop(poll_interval=0.01))
    await asyncio.sleep(0.05)
    dispatcher.stop()
    await loop_task
