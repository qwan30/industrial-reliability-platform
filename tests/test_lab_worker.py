"""Unit tests for LabWorker."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from industrial_reliability.lab.worker import LabWorker


def test_lab_worker_init_and_shutdown() -> None:
    mock_pool = MagicMock()
    worker_id = uuid4()
    worker = LabWorker(mock_pool, worker_id=worker_id)
    assert worker.worker_id == worker_id
    assert not worker._shutdown_event.is_set()

    worker.shutdown()
    assert worker._shutdown_event.is_set()


@pytest.mark.asyncio
async def test_lab_worker_run_and_shutdown() -> None:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    worker = LabWorker(mock_pool)
    worker.outbox.start = AsyncMock()
    worker.outbox.stop = AsyncMock()
    worker.outbox.dispatch_batch = AsyncMock(return_value=0)

    # Schedule shutdown after 50ms
    async def trigger_shutdown() -> None:
        await asyncio.sleep(0.05)
        worker.shutdown()

    shutdown_task = asyncio.create_task(trigger_shutdown())
    await worker.run()
    await shutdown_task
    worker.outbox.start.assert_called_once()
    worker.outbox.stop.assert_called_once()
