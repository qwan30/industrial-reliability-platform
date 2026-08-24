from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from industrial_reliability.api import create_app
from industrial_reliability.console_stream import ConsoleEventBroker, ConsoleEventV1
from industrial_reliability.kafka_io import decode_message
from industrial_reliability.persistence import (
    AlertSummaryRecord,
    ReplaySessionRecord,
)
from industrial_reliability.runtime_messages import (
    REPLAY_COMMANDS_TOPIC,
    ReplayCommandV1,
)


class FakeScorer:
    def __init__(self) -> None:
        self.model_version = "champion-statistical-v1"
        self.manifest = {
            "source_dataset_sha256": "a" * 64,
            "contract_sha256": "b" * 64,
        }

    def score(self, feature: Any) -> Any:
        return MagicMock(score=1.5, threshold=1.0, is_anomaly=True, evidence_vector=())


class FakeProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes, bytes]] = []

    def send(self, topic: str, key: bytes, value: bytes) -> None:
        self.messages.append((topic, key, value))


class FakeStore:
    def __init__(self) -> None:
        self.replays: dict[UUID, ReplaySessionRecord] = {}
        self.alerts: dict[UUID, list[AlertSummaryRecord]] = {}
        self.events: dict[str, list[ConsoleEventV1]] = {}

    def get_replay(self, session_id: UUID) -> ReplaySessionRecord | None:
        return self.replays.get(session_id)

    def list_alerts(
        self, session_id: UUID, after: UUID | None = None, limit: int = 50
    ) -> list[AlertSummaryRecord]:
        return self.alerts.get(session_id, [])

    def get_alert_detail(self, alert_id: UUID) -> Any:
        return None

    def events_after(
        self, session_id: str, after_event_id: str | None = None, limit: int = 100
    ) -> tuple[ConsoleEventV1, ...]:
        all_ev = self.events.get(session_id, [])
        if after_event_id is None:
            return tuple(all_ev[:limit])
        for i, ev in enumerate(all_ev):
            if ev.event_id == after_event_id:
                return tuple(all_ev[i + 1 : i + 1 + limit])
        return ()


def test_start_replay_publishes_versioned_command() -> None:
    scorer = FakeScorer()
    producer = FakeProducer()
    app = create_app(scorer=scorer, producer=producer)
    client = TestClient(app)

    response = client.post(
        "/v1/replays",
        json={
            "range_start": "2020-04-17T23:00:00",
            "range_end": "2020-04-18T02:00:00",
            "speed": 100,
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["success"] is True
    session_id = data["data"]["replay_session_id"]
    assert session_id is not None

    assert len(producer.messages) == 1
    topic, _key, val = producer.messages[0]
    assert topic == REPLAY_COMMANDS_TOPIC
    cmd = decode_message(val, ReplayCommandV1)
    assert cmd.action == "START"
    assert cmd.speed == 100
    assert cmd.range_start == datetime(2020, 4, 17, 23, 0)
    assert cmd.range_end == datetime(2020, 4, 18, 2, 0)


def test_start_replay_validation_errors() -> None:
    scorer = FakeScorer()
    app = create_app(scorer=scorer)
    client = TestClient(app)

    # Invalid range (start >= end)
    res1 = client.post(
        "/v1/replays",
        json={
            "range_start": "2020-04-18T02:00:00",
            "range_end": "2020-04-17T23:00:00",
            "speed": 100,
        },
    )
    assert res1.status_code == 422

    # Invalid speed
    res2 = client.post(
        "/v1/replays",
        json={
            "range_start": "2020-04-17T23:00:00",
            "range_end": "2020-04-18T02:00:00",
            "speed": 50,  # only 1, 100, 1000 allowed
        },
    )
    assert res2.status_code == 422


def test_control_replay_publishes_command() -> None:
    scorer = FakeScorer()
    producer = FakeProducer()
    app = create_app(scorer=scorer, producer=producer)
    client = TestClient(app)

    session_id = uuid4()
    response = client.post(
        f"/v1/replays/{session_id}/commands",
        json={"action": "PAUSE"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["success"] is True

    assert len(producer.messages) == 1
    _topic, _key, val = producer.messages[0]
    cmd = decode_message(val, ReplayCommandV1)
    assert cmd.action == "PAUSE"
    assert cmd.replay_session_id == session_id


@pytest.mark.asyncio
async def test_sse_stream_snapshot_and_replay_history() -> None:
    scorer = FakeScorer()
    store = FakeStore()
    session_id = uuid4()

    store.replays[session_id] = ReplaySessionRecord(
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        model_version="champion-statistical-v1",
        state="RUNNING",
        last_sequence=10,
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        error_code=None,
        updated_at=datetime(2026, 8, 24, 12, 0),
    )

    ev1 = ConsoleEventV1(
        event_id="dec-1",
        replay_session_id=str(session_id),
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        payload={"score": 1.5},
        durable=True,
    )
    ev2 = ConsoleEventV1(
        event_id="dec-2",
        replay_session_id=str(session_id),
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 10),
        payload={"score": 1.1},
        durable=True,
    )
    store.events[str(session_id)] = [ev1, ev2]

    # Without broker: emits snapshot and missed events, then closes cleanly
    app = create_app(scorer=scorer, store=store, broker=None)  # type: ignore[arg-type]
    client = TestClient(app)

    # Reconnect with Last-Event-ID pointing to dec-1: should get snapshot + dec-2
    res = client.get(
        f"/v1/replays/{session_id}/stream",
        headers={"Last-Event-ID": "dec-1"},
    )
    assert res.status_code == 200
    assert "event: snapshot" in res.text
    assert "event: score" in res.text
    assert "dec-2" in res.text

    # Reconnect with unknown Last-Event-ID: should get resync_required + snapshot
    res2 = client.get(
        f"/v1/replays/{session_id}/stream",
        headers={"Last-Event-ID": "unknown-id"},
    )
    assert res2.status_code == 200
    assert "event: resync_required" in res2.text
    assert "event: snapshot" in res2.text


@pytest.mark.asyncio
async def test_sse_stream_with_live_broker_events() -> None:
    broker = ConsoleEventBroker()
    session_id = uuid4()

    # Test broker subscription directly
    q = await broker.subscribe(str(session_id))
    assert broker.subscriber_count(str(session_id)) == 1

    ev = ConsoleEventV1(
        event_id="live-1",
        replay_session_id=str(session_id),
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 15),
        payload={"score": 2.0},
        durable=True,
    )
    broker.publish(ev)

    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert isinstance(received, ConsoleEventV1)
    assert received.event_id == "live-1"

    await broker.unsubscribe(str(session_id), q)
    assert broker.subscriber_count(str(session_id)) == 0
