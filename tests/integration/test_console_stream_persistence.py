from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from industrial_reliability.console_stream import ConsoleEventV1
from industrial_reliability.persistence import RuntimeStore
from industrial_reliability.runtime_messages import ReplayStatusV1

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp")


@pytest.fixture
def store() -> RuntimeStore:
    try:
        store = RuntimeStore(TEST_DB_URL)
        store.check_connection(timeout=1.0)
        # Apply schema if needed
        from pathlib import Path

        migration1 = (
            Path(__file__).resolve().parents[2] / "db" / "migrations" / "001_alert_lifecycle.sql"
        )
        if migration1.is_file():
            store.execute_script(migration1.read_text(encoding="utf-8"))
        migration2 = (
            Path(__file__).resolve().parents[2] / "db" / "migrations" / "002_console_stream.sql"
        )
        if migration2.is_file():
            store.execute_script(migration2.read_text(encoding="utf-8"))
        return store
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable at {TEST_DB_URL}: {exc}")


def test_durable_event_insert_is_idempotent(store: RuntimeStore) -> None:
    session_id = uuid4()
    # Create replay session first to satisfy foreign key
    status = ReplayStatusV1(
        schema_version="replay-status-v1",
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 4, 18, 0, 0),
        emitted_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
        state="RUNNING",
        last_sequence=1,
    )
    store.record_replay_status(status)

    event = ConsoleEventV1(
        event_id=f"decision-{uuid4()}",
        replay_session_id=str(session_id),
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        payload={"score": 1.5, "is_anomaly": True},
        durable=True,
    )

    store.append_console_event(event)
    store.append_console_event(event)  # duplicate insert

    events = store.events_after(str(session_id), after_event_id=None)
    assert len(events) == 1
    assert events[0].event_id == event.event_id
    assert events[0].payload == event.payload

    # Append second event
    event2 = ConsoleEventV1(
        event_id=f"decision-{uuid4()}",
        replay_session_id=str(session_id),
        event_type="score",
        source_timestamp=datetime(2020, 4, 18, 0, 10),
        payload={"score": 1.2, "is_anomaly": False},
        durable=True,
    )
    store.append_console_event(event2)

    events_after_1 = store.events_after(str(session_id), after_event_id=event.event_id)
    assert len(events_after_1) == 1
    assert events_after_1[0].event_id == event2.event_id
