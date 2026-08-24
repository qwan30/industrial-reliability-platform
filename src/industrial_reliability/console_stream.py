"""Console event feed, downsampling, and in-memory broker for Phase 6."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from industrial_reliability.kafka_io import decode_message
from industrial_reliability.runtime_messages import (
    AlertEventV1,
    ReplayStatusV1,
    ScoreDecisionV1,
    TelemetryEventV1,
)


@dataclass(frozen=True, slots=True)
class ConsoleEventV1:
    event_id: str
    replay_session_id: str
    event_type: Literal["status", "telemetry", "score", "alert"]
    source_timestamp: datetime
    payload: Mapping[str, Any]
    durable: bool


class TelemetryDownsampler:
    def __init__(self, interval_seconds: int = 60) -> None:
        self.interval_seconds = interval_seconds
        self._last_emitted_by_machine: dict[str, datetime] = {}

    def accept(self, event: ConsoleEventV1) -> bool:
        machine_id = str(event.payload.get("machine_id", "default"))
        last_ts = self._last_emitted_by_machine.get(machine_id)
        if (
            last_ts is None
            or (event.source_timestamp - last_ts).total_seconds() >= self.interval_seconds
        ):
            self._last_emitted_by_machine[machine_id] = event.source_timestamp
            return True
        return False


class ConsoleEventBroker:
    def __init__(self, max_queue_size: int = 256) -> None:
        self.max_queue_size = max_queue_size
        self._subscribers: dict[str, set[asyncio.Queue[ConsoleEventV1 | str]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, replay_session_id: str) -> asyncio.Queue[ConsoleEventV1 | str]:
        q: asyncio.Queue[ConsoleEventV1 | str] = asyncio.Queue(maxsize=self.max_queue_size)
        async with self._lock:
            self._subscribers[replay_session_id].add(q)
        return q

    async def unsubscribe(
        self, replay_session_id: str, queue: asyncio.Queue[ConsoleEventV1 | str]
    ) -> None:
        async with self._lock:
            if replay_session_id in self._subscribers:
                self._subscribers[replay_session_id].discard(queue)
                if not self._subscribers[replay_session_id]:
                    del self._subscribers[replay_session_id]

    def subscriber_count(self, replay_session_id: str) -> int:
        return len(self._subscribers.get(replay_session_id, ()))

    def publish(self, event: ConsoleEventV1) -> None:
        subscribers = list(self._subscribers.get(event.replay_session_id, ()))
        for q in subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    while not q.empty():
                        q.get_nowait()
                    q.put_nowait("resync_required")
                except (asyncio.QueueFull, asyncio.QueueEmpty):
                    pass


class ConsoleFeed:
    def __init__(
        self,
        store: Any,
        broker: ConsoleEventBroker,
        telemetry_interval_seconds: int = 60,
        consumer: Any = None,
    ) -> None:
        self.store = store
        self.broker = broker
        self.downsampler = TelemetryDownsampler(interval_seconds=telemetry_interval_seconds)
        self.consumer = consumer

    def _decode(self, record: Any) -> ConsoleEventV1:
        if isinstance(record, ConsoleEventV1):
            return record

        topic = getattr(record, "topic", "")
        value = getattr(record, "value", b"")

        if topic == "irp.telemetry.v1" or b'"telemetry-event-v1"' in value:
            msg_t = decode_message(value, TelemetryEventV1)
            return ConsoleEventV1(
                event_id=str(msg_t.message_id),
                replay_session_id=str(msg_t.replay_session_id),
                event_type="telemetry",
                source_timestamp=msg_t.source_timestamp,
                payload=msg_t.model_dump(mode="json"),
                durable=False,
            )
        elif topic == "irp.scores.v1" or b'"score-decision-v1"' in value:
            msg_s = decode_message(value, ScoreDecisionV1)
            return ConsoleEventV1(
                event_id=str(msg_s.decision_id),
                replay_session_id=str(msg_s.replay_session_id),
                event_type="score",
                source_timestamp=msg_s.source_timestamp,
                payload=msg_s.model_dump(mode="json"),
                durable=True,
            )
        elif topic == "irp.alerts.v1" or b'"alert-event-v1"' in value:
            msg_a = decode_message(value, AlertEventV1)
            return ConsoleEventV1(
                event_id=str(msg_a.message_id),
                replay_session_id=str(msg_a.replay_session_id),
                event_type="alert",
                source_timestamp=msg_a.source_timestamp,
                payload=msg_a.model_dump(mode="json"),
                durable=True,
            )
        else:
            msg_r = decode_message(value, ReplayStatusV1)
            return ConsoleEventV1(
                event_id=f"status-{msg_r.replay_session_id}-{msg_r.state}-{getattr(msg_r, 'last_sequence', 0)}",
                replay_session_id=str(msg_r.replay_session_id),
                event_type="status",
                source_timestamp=msg_r.source_timestamp or datetime.fromtimestamp(0),
                payload=msg_r.model_dump(mode="json"),
                durable=True,
            )

    def process(self, record: Any) -> ConsoleEventV1 | None:
        event = self._decode(record)
        if event.event_type == "telemetry" and not self.downsampler.accept(event):
            if self.consumer is not None and hasattr(self.consumer, "commit"):
                self.consumer.commit(record)
            return None

        if event.durable:
            self.store.append_console_event(event)

        self.broker.publish(event)
        if self.consumer is not None and hasattr(self.consumer, "commit"):
            self.consumer.commit(record)
        return event
