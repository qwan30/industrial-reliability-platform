"""Background worker supervising simulation engine, outbox, and health heartbeats."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool

from industrial_reliability.lab.engine import SimulationEngine
from industrial_reliability.lab.outbox import LabOutboxPublisher

logger = logging.getLogger("industrial_reliability.lab.worker")


class LabWorker:
    """Worker process supervising simulation engine and telemetry dispatch."""

    def __init__(
        self,
        pool: ConnectionPool,
        worker_id: UUID | None = None,
    ) -> None:
        self.pool = pool
        self.worker_id = worker_id or uuid4()
        self.engine = SimulationEngine(pool, self.worker_id)
        self.outbox = LabOutboxPublisher(pool)
        self._shutdown_event = asyncio.Event()

    async def _heartbeat_loop(self) -> None:
        """Write worker heartbeat every 1 second for readiness probe."""
        while not self._shutdown_event.is_set():
            try:
                with self.pool.connection(timeout=2.0) as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO lab_worker_health (worker_id, heartbeat_at, kafka_connected, analyst_last_poll_at)
                        VALUES (%s, now(), %s, now())
                        ON CONFLICT (worker_id) DO UPDATE
                        SET heartbeat_at = now(),
                            kafka_connected = EXCLUDED.kafka_connected,
                            analyst_last_poll_at = now()
                        """,
                        (str(self.worker_id), self.outbox._running),
                    )
                    conn.commit()
            except Exception as e:
                logger.warning("Heartbeat failed: %s", e)

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=1.0)

    async def _outbox_loop(self) -> None:
        """Poll and dispatch outbox records."""
        while not self._shutdown_event.is_set():
            try:
                dispatched = await self.outbox.dispatch_batch(limit=100)
                if dispatched == 0:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._shutdown_event.wait(), timeout=0.1)
            except Exception as e:
                logger.error("Outbox dispatch loop error: %s", e)
                await asyncio.sleep(1.0)

    async def run(self) -> None:
        """Main worker execution loop."""
        logger.info("Starting LabWorker %s", self.worker_id)
        await self.outbox.start()

        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        outbox_task = asyncio.create_task(self._outbox_loop())

        try:
            await self._shutdown_event.wait()
        finally:
            heartbeat_task.cancel()
            outbox_task.cancel()
            await self.outbox.stop()
            logger.info("LabWorker %s stopped", self.worker_id)

    def shutdown(self) -> None:
        self._shutdown_event.set()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    dsn = (
        os.environ.get("LAB_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql://irp:irp_password@127.0.0.1:5432/irp"
    )

    pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=8, open=False)
    pool.open()

    worker = LabWorker(pool)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def sig_handler() -> None:
        worker.shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, sig_handler)

    try:
        loop.run_until_complete(worker.run())
    finally:
        pool.close()
        loop.close()


if __name__ == "__main__":
    main()
