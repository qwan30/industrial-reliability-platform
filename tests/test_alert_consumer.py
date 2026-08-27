from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from prometheus_client import CollectorRegistry

from industrial_reliability.alert_consumer import (
    AlertConsumer,
    AlertOutboxDispatcher,
    ProcessOutcome,
)
from industrial_reliability.alert_state import AlertState
from industrial_reliability.kafka_io import encode_message
from industrial_reliability.metrics import build_runtime_metrics
from industrial_reliability.persistence import OutboxRow, RuntimeStore
from tests.test_persistence import _make_decision, _make_policy


class MockKafkaRecord:
    def __init__(self, value: bytes, topic: str = "irp.scores.v1", offset: int = 0) -> None:
        self.value = value
        self.topic = topic
        self.offset = offset


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
async def test_consumer_records_only_persisted_transition_metrics() -> None:
    metrics = build_runtime_metrics(CollectorRegistry())
    policy = _make_policy()
    session_id = uuid4()
    mock_store = MagicMock(spec=RuntimeStore)
    mock_store.load_alert_state.return_value = AlertState.empty(session_id, "metropt3")
    mock_store.count_active_alerts.return_value = 1
    consumer = AlertConsumer(store=mock_store, policy=policy, metrics=metrics)

    # 1. Anomalous decision opens an alert -> metric recorded
    decision = _make_decision(session_id, is_anomaly=True)
    record = MockKafkaRecord(encode_message(decision))
    assert await consumer.process(record) == ProcessOutcome.COMMITTED
    assert metrics.alert_events.labels(action="opened")._value.get() == 1
    assert metrics.alerts_active._value.get() == 1

    # 2. No-event decision -> counter does not increment
    mock_store.count_active_alerts.return_value = 1
    normal_decision = _make_decision(session_id, is_anomaly=False)
    normal_record = MockKafkaRecord(encode_message(normal_decision))
    assert await consumer.process(normal_record) == ProcessOutcome.COMMITTED
    assert metrics.alert_events.labels(action="opened")._value.get() == 1


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
