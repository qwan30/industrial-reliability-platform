from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from industrial_reliability.console_stream import (
    ConsoleEventBroker,
    ConsoleEventV1,
    ConsoleFeed,
)
from industrial_reliability.kafka_io import encode_message
from industrial_reliability.runtime_messages import (
    AlertEventV1,
    EvidenceValueV1,
    ReplayStatusV1,
    ScoreDecisionV1,
    TelemetryEventV1,
)


class FakeStore:
    def __init__(self) -> None:
        self.console_events: list[ConsoleEventV1] = []

    def append_console_event(self, event: ConsoleEventV1) -> None:
        self.console_events.append(event)


class FakeConsumer:
    def __init__(self) -> None:
        self.committed_records: list[Any] = []

    def commit(self, record: Any) -> None:
        self.committed_records.append(record)


class FakeRecord:
    def __init__(self, value: bytes, topic: str = "") -> None:
        self.value = value
        self.topic = topic


def _telemetry_record(ts: datetime, machine_id: str = "metropt3") -> FakeRecord:
    session_id = uuid4()
    event = TelemetryEventV1(
        schema_version="telemetry-event-v1",
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=ts,
        emitted_at=datetime.now(UTC),
        machine_id=machine_id,
        sequence=1,
        tp2=1.0,
        tp3=2.0,
        h1=0.5,
        dv_pressure=0.0,
        reservoirs=8.0,
        oil_temperature=60.0,
        motor_current=3.5,
        comp=1,
        dv_electric=0,
        towers=1,
        mpg=1,
        lps=0,
        pressure_switch=0,
        oil_level=1,
        caudal_impulses=1,
    )
    return FakeRecord(encode_message(event), topic="irp.telemetry.v1")


def _score_record(session_id: str | None = None) -> FakeRecord:
    sid = uuid4() if session_id is None else UUID(session_id)
    decision = ScoreDecisionV1(
        message_id=uuid4(),
        replay_session_id=sid,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        emitted_at=datetime.now(UTC),
        decision_id=uuid4(),
        window_id=uuid4(),
        model_version="champion-statistical-v1",
        score=1.5,
        threshold=1.0,
        is_anomaly=True,
        evidence_vector=(
            EvidenceValueV1(
                feature_name="tp2_mean",
                feature_value=1.5,
                robust_deviation=0.5,
            ),
        ),
    )
    return FakeRecord(encode_message(decision), topic="irp.scores.v1")


def _alert_record() -> FakeRecord:
    session_id = uuid4()
    alert_id = uuid4()
    event = AlertEventV1(
        schema_version="alert-event-v1",
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        emitted_at=datetime.now(UTC),
        alert_id=alert_id,
        machine_id="metropt3",
        action="OPENED",
        first_detection=datetime(2020, 4, 18, 0, 0),
        last_detection=datetime(2020, 4, 18, 0, 5),
        decision_ids=(uuid4(),),
        policy_sha256="c" * 64,
    )
    return FakeRecord(encode_message(event), topic="irp.alerts.v1")


def _status_record() -> FakeRecord:
    session_id = uuid4()
    event = ReplayStatusV1(
        schema_version="replay-status-v1",
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 4, 18, 0, 0),
        emitted_at=datetime.now(UTC),
        state="RUNNING",
        last_sequence=10,
    )
    return FakeRecord(encode_message(event), topic="irp.replay.status.v1")


def test_telemetry_downsamples_by_source_time() -> None:
    store = FakeStore()
    broker = ConsoleEventBroker()
    consumer = FakeConsumer()
    feed = ConsoleFeed(
        store=store,
        broker=broker,
        telemetry_interval_seconds=60,
        consumer=consumer,
    )

    published_events: list[ConsoleEventV1] = []
    base_time = datetime(2020, 4, 18, 0, 0, 0)
    for seconds in (0, 10, 59, 60):
        rec = _telemetry_record(base_time + timedelta(seconds=seconds))
        ev = feed.process(rec)
        if ev is not None:
            published_events.append(ev)

    assert [event.source_timestamp.second for event in published_events] == [0, 0]
    assert store.console_events == []
    assert len(consumer.committed_records) == 4


def test_durable_events_saved_to_store_and_published() -> None:
    store = FakeStore()
    broker = ConsoleEventBroker()
    consumer = FakeConsumer()
    feed = ConsoleFeed(
        store=store,
        broker=broker,
        telemetry_interval_seconds=60,
        consumer=consumer,
    )

    score_rec = _score_record()
    score_ev = feed.process(score_rec)
    assert score_ev is not None
    assert score_ev.durable is True
    assert score_ev.event_type == "score"
    assert len(store.console_events) == 1

    alert_rec = _alert_record()
    alert_ev = feed.process(alert_rec)
    assert alert_ev is not None
    assert alert_ev.durable is True
    assert alert_ev.event_type == "alert"
    assert len(store.console_events) == 2

    status_rec = _status_record()
    status_ev = feed.process(status_rec)
    assert status_ev is not None
    assert status_ev.durable is True
    assert status_ev.event_type == "status"
    assert len(store.console_events) == 3


@pytest.mark.asyncio
async def test_broker_publishes_to_subscribers_and_handles_slow_subscriber() -> None:
    broker = ConsoleEventBroker(max_queue_size=2)
    session_id = str(uuid4())

    q = await broker.subscribe(session_id)
    assert broker.subscriber_count(session_id) == 1

    ev1 = ConsoleEventV1(
        event_id="e1",
        replay_session_id=session_id,
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 0),
        payload={"score": 1.0},
        durable=True,
    )
    ev2 = ConsoleEventV1(
        event_id="e2",
        replay_session_id=session_id,
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        payload={"score": 1.1},
        durable=True,
    )
    ev3 = ConsoleEventV1(
        event_id="e3",
        replay_session_id=session_id,
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 10),
        payload={"score": 1.2},
        durable=True,
    )

    broker.publish(ev1)
    broker.publish(ev2)
    # Queue is now full (size 2), publishing ev3 should put "resync_required"
    broker.publish(ev3)

    item = q.get_nowait()
    assert item == "resync_required"

    await broker.unsubscribe(session_id, q)
    assert broker.subscriber_count(session_id) == 0
