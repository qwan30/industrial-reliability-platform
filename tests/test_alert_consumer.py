from __future__ import annotations

import asyncio
import hashlib
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
from industrial_reliability.kafka_io import decode_message, encode_message
from industrial_reliability.metrics import build_runtime_metrics
from industrial_reliability.persistence import OutboxRow, RuntimeStore
from industrial_reliability.runtime_messages import QuarantineRecordV1
from tests.test_persistence import _make_decision, _make_policy


class MockKafkaRecord:
    def __init__(
        self,
        value: bytes,
        topic: str = "irp.scores.v1",
        offset: int = 0,
        partition: int = 0,
    ) -> None:
        self.value = value
        self.topic = topic
        self.offset = offset
        self.partition = partition


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
async def test_invalid_score_is_durably_quarantined_before_commit() -> None:
    policy = _make_policy()
    mock_store = MagicMock(spec=RuntimeStore)
    mock_producer = AsyncMock()
    consumer = AlertConsumer(store=mock_store, policy=policy, producer=mock_producer)

    bad_payload = b"invalid_score_json_bytes"
    bad_record = MockKafkaRecord(
        value=bad_payload,
        topic="irp.scores.v1",
        offset=123,
        partition=2,
    )

    outcome = await consumer.process(bad_record)
    assert outcome == ProcessOutcome.QUARANTINED

    # Verify producer sent to QUARANTINE_TOPIC
    assert mock_producer.send_and_wait.called
    call_args = mock_producer.send_and_wait.call_args
    topic_called = call_args[0][0] if call_args[0] else call_args[1].get("topic")
    assert topic_called == "irp.quarantine.v1"

    # Decode and verify the quarantined payload
    sent_value = call_args[1].get("value") if "value" in call_args[1] else call_args[0][1]
    quarantine = decode_message(sent_value, QuarantineRecordV1)
    expected_hash = hashlib.sha256(bad_payload).hexdigest()

    assert quarantine.original_topic == "irp.scores.v1"
    assert quarantine.partition == 2
    assert quarantine.offset == 123
    assert quarantine.payload_sha256 == expected_hash
    assert quarantine.error_code == "INVALID_SCORE_PAYLOAD"
    assert len(quarantine.error_detail) > 0
    assert quarantine.source_dataset_sha256 == "0" * 64
    assert quarantine.contract_sha256 == "0" * 64

    # Verify error is raised if producer is None
    consumer_no_producer = AlertConsumer(store=mock_store, policy=policy, producer=None)
    with pytest.raises(
        RuntimeError, match="Kafka producer is required to quarantine invalid scores"
    ):
        await consumer_no_producer.process(bad_record)

    # Verify error during send_and_wait is not swallowed
    failing_producer = AsyncMock()
    failing_producer.send_and_wait.side_effect = RuntimeError("Kafka broker down")
    consumer_failing_producer = AlertConsumer(
        store=mock_store, policy=policy, producer=failing_producer
    )
    with pytest.raises(RuntimeError, match="Kafka broker down"):
        await consumer_failing_producer.process(bad_record)


@pytest.mark.asyncio
async def test_alert_consumer_decode_error_and_skipped() -> None:
    policy = _make_policy()
    mock_store = MagicMock(spec=RuntimeStore)
    mock_producer = AsyncMock()
    consumer = AlertConsumer(store=mock_store, policy=policy, producer=mock_producer)

    # 1. Invalid payload
    bad_record = MockKafkaRecord(b"not_valid_json")
    outcome = await consumer.process(bad_record)
    assert outcome == ProcessOutcome.QUARANTINED
    assert mock_producer.send_and_wait.called

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
