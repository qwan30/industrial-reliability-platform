"""Unit tests for LabOutboxPublisher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from industrial_reliability.lab.outbox import LabOutboxPublisher


@pytest.mark.asyncio
async def test_outbox_publisher_start_and_stop() -> None:
    mock_pool = MagicMock()
    pub = LabOutboxPublisher(mock_pool, bootstrap_servers="localhost:9092")
    assert pub._running is False

    with (
        patch("aiokafka.AIOKafkaProducer.start", new_callable=AsyncMock) as mock_start,
        patch("aiokafka.AIOKafkaProducer.stop", new_callable=AsyncMock) as mock_stop,
    ):
        await pub.start()
        assert pub._running is True
        mock_start.assert_called_once()

        await pub.stop()
        assert pub._running is False
        mock_stop.assert_called_once()


def test_publish_pending_sync_empty() -> None:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.return_value = []

    pub = LabOutboxPublisher(mock_pool)
    count = pub.publish_pending_sync(limit=50)
    assert count == 0


def test_publish_pending_sync_with_records() -> None:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    msg_id = str(uuid4())
    mock_cur.fetchall.return_value = [
        {
            "message_id": msg_id,
            "run_id": str(uuid4()),
            "sensor_id": str(uuid4()),
            "tick": 20,
            "topic": "irp.lab.observations.v1",
            "payload": {"value": 400000.0},
        }
    ]

    pub = LabOutboxPublisher(mock_pool)
    count = pub.publish_pending_sync(limit=10)
    assert count == 1
    mock_conn.commit.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_batch_not_running() -> None:
    mock_pool = MagicMock()
    pub = LabOutboxPublisher(mock_pool)
    assert await pub.dispatch_batch() == 0


@pytest.mark.asyncio
async def test_dispatch_batch_with_records() -> None:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    msg_id = str(uuid4())
    run_id = str(uuid4())
    sensor_id = str(uuid4())
    mock_cur.fetchall.return_value = [
        {
            "message_id": msg_id,
            "run_id": run_id,
            "sensor_id": sensor_id,
            "tick": 20,
            "topic": "irp.lab.observations.v1",
            "payload": {"value": 400000.0, "asset_id": "asset-1"},
        }
    ]

    pub = LabOutboxPublisher(mock_pool)
    mock_producer = MagicMock()
    mock_producer.send_and_wait = AsyncMock()
    pub._producer = mock_producer
    pub._running = True

    count = await pub.dispatch_batch(limit=10)
    assert count == 1
    mock_producer.send_and_wait.assert_called_once()
    mock_conn.commit.assert_called_once()
