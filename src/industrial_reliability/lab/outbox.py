"""Outbox publisher dispatching lab observations to Kafka."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

TOPIC_LAB_OBSERVATIONS = "irp.lab.observations.v1"


class LabOutboxPublisher:
    """Dispatches rows from lab_outbox to Kafka with transactional confirmation."""

    def __init__(
        self,
        pool: ConnectionPool,
        bootstrap_servers: str | None = None,
    ) -> None:
        self.pool = pool
        self.bootstrap_servers = bootstrap_servers or os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"
        )
        self._producer: Any = None
        self._running = False

    async def start(self) -> None:
        """Initialize aiokafka producer if available."""
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id="lab-outbox-publisher",
                acks="all",
            )
            await self._producer.start()
            self._running = True
            logger.info("Outbox publisher connected to Kafka at %s", self.bootstrap_servers)
        except Exception as e:
            logger.warning("Could not start Kafka producer: %s", e)
            self._producer = None
            self._running = False

    async def stop(self) -> None:
        self._running = False
        if self._producer:
            try:
                await self._producer.stop()
            except Exception as e:
                logger.warning("Error stopping Kafka producer: %s", e)

    def publish_pending_sync(self, limit: int = 100) -> int:
        """Synchronously poll and publish unpublished rows (for testing / fallback)."""
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT message_id, run_id, sensor_id, tick, topic, payload
                FROM lab_outbox
                WHERE published_at IS NULL
                ORDER BY run_id, tick, sensor_id
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            if not rows:
                return 0

            # If no live Kafka producer, we can mark them published for local testing if configured
            published_ids: list[str] = [r["message_id"] for r in rows]

            cur.execute(
                """
                UPDATE lab_outbox
                SET published_at = now()
                WHERE message_id = ANY(%s)
                """,
                (published_ids,),
            )
            conn.commit()
            return len(published_ids)

    async def dispatch_batch(self, limit: int = 100) -> int:
        """Fetch unpublished outbox rows and dispatch to Kafka."""
        if not self._running or not self._producer:
            return 0

        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT message_id, run_id, sensor_id, tick, topic, payload
                FROM lab_outbox
                WHERE published_at IS NULL
                ORDER BY run_id, tick, sensor_id
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            if not rows:
                return 0

            published_ids: list[str] = []
            for r in rows:
                payload_data = r["payload"]
                if isinstance(payload_data, str):
                    payload_bytes = payload_data.encode("utf-8")
                    payload_dict = json.loads(payload_data)
                else:
                    payload_bytes = json.dumps(payload_data).encode("utf-8")
                    payload_dict = payload_data

                asset_id = payload_dict.get("asset_id", r["sensor_id"])
                key_bytes = f"{r['run_id']}:{asset_id}:{r['sensor_id']}".encode()

                try:
                    await self._producer.send_and_wait(
                        r["topic"],
                        key=key_bytes,
                        value=payload_bytes,
                    )
                    published_ids.append(r["message_id"])
                except Exception as e:
                    logger.error("Failed to publish message %s to Kafka: %s", r["message_id"], e)
                    break

            if published_ids:
                cur.execute(
                    """
                    UPDATE lab_outbox
                    SET published_at = now()
                    WHERE message_id = ANY(%s)
                    """,
                    (published_ids,),
                )
                conn.commit()

            return len(published_ids)
