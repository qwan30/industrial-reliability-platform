"""Async service running the alert lifecycle consumer and outbox dispatcher."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from industrial_reliability.alert_consumer import (
    AlertConsumer,
    AlertOutboxDispatcher,
    ProcessOutcome,
)
from industrial_reliability.alert_policy import (
    LockedAlertPolicyV1,
    verify_policy_integrity,
)
from industrial_reliability.kafka_io import KafkaSettings
from industrial_reliability.metrics import (
    RuntimeMetrics,
    build_runtime_metrics,
    start_process_metrics,
)
from industrial_reliability.persistence import RuntimeStore
from industrial_reliability.runtime_messages import (
    SCORES_TOPIC,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertServiceSettings:
    kafka: KafkaSettings
    database_url: str
    policy_path: Path
    machine_id: str = "metropt3"
    metrics_port: int | None = None

    @classmethod
    def from_env(cls) -> AlertServiceSettings:
        kafka_settings = KafkaSettings.from_env()
        db_url = os.environ.get("DATABASE_URL", "").strip()
        if not db_url:
            raise ValueError("DATABASE_URL must be set in the environment")

        policy_path_str = os.environ.get("ALERT_POLICY_PATH", "").strip()
        if not policy_path_str:
            # Only research-candidate packages embed the locked alert policy
            # (champion packages do not ship one), so the fallback default
            # points at the research candidate. Compose deployments always
            # set SCORING_PACKAGE_DIR explicitly.
            pkg_dir_str = (
                os.environ.get("SCORING_PACKAGE_DIR")
                or os.environ.get("CHAMPION_PACKAGE_DIR")
                or "artifacts/research-candidate"
            ).strip()
            policy_path = Path(pkg_dir_str) / "alert-policy.json"
        else:
            policy_path = Path(policy_path_str)

        metrics_port_str = os.environ.get("METRICS_PORT", "").strip()
        metrics_port = int(metrics_port_str) if metrics_port_str else None
        machine_id = os.environ.get("MACHINE_ID", "metropt3").strip()

        return cls(
            kafka=kafka_settings,
            database_url=db_url,
            policy_path=policy_path,
            machine_id=machine_id,
            metrics_port=metrics_port,
        )


class AlertService:
    def __init__(
        self,
        settings: AlertServiceSettings,
        metrics: RuntimeMetrics | None = None,
    ) -> None:
        self.settings = settings
        self.metrics = metrics
        self.store = RuntimeStore(settings.database_url)
        policy_data = json.loads(settings.policy_path.read_text(encoding="utf-8"))
        self.policy = LockedAlertPolicyV1(**policy_data)
        verify_policy_integrity(self.policy)
        self.producer: AIOKafkaProducer | None = None
        self.consumer: AIOKafkaConsumer | None = None
        self.alert_consumer: AlertConsumer | None = None
        self.outbox_dispatcher: AlertOutboxDispatcher | None = None
        self._running = False
        self._consumer_task: asyncio.Task[None] | None = None
        self._outbox_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka.bootstrap_servers,
            client_id=f"{self.settings.kafka.client_id}-alert-producer",
            acks="all",
            enable_idempotence=True,
        )
        self.consumer = AIOKafkaConsumer(
            SCORES_TOPIC,
            bootstrap_servers=self.settings.kafka.bootstrap_servers,
            client_id=f"{self.settings.kafka.client_id}-alert-consumer",
            group_id="irp-alert-service-v1",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self.producer.start()
        await self.consumer.start()

        self.alert_consumer = AlertConsumer(
            store=self.store,
            policy=self.policy,
            producer=self.producer,
            consumer=self.consumer,
            machine_id=self.settings.machine_id,
        )
        self.outbox_dispatcher = AlertOutboxDispatcher(
            store=self.store,
            producer=self.producer,
        )
        self._running = True
        self._consumer_task = asyncio.create_task(self._run_consumer_loop())
        self._outbox_task = asyncio.create_task(self.outbox_dispatcher.run_loop())

    async def stop(self) -> None:
        self._running = False
        if self.outbox_dispatcher:
            self.outbox_dispatcher.stop()
        if self._outbox_task and not self._outbox_task.done():
            self._outbox_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._outbox_task
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def _process_consumer_batch(self, batch: Any) -> bool:
        """Process one consumer batch; return True when the loop must halt.

        A ``SESSION_FAILED`` outcome must not commit the failed offset (the
        record is preserved for inspection), so re-polling would immediately
        re-fetch and re-fail the same record in a hot loop. Callers must halt
        consumption instead of re-polling without delay.
        """
        if self.consumer is None or self.alert_consumer is None:
            return False
        for tp, messages in batch.items():
            for record in messages:
                outcome = await self.alert_consumer.process(record)
                if outcome == ProcessOutcome.SESSION_FAILED:
                    logger.error(
                        "Session failed for record at offset %d; halting partition commit to preserve failed record",
                        record.offset,
                    )
                    return True
                await self.consumer.commit({tp: record.offset + 1})
        return False

    async def _run_consumer_loop(self) -> None:
        if self.consumer is None or self.alert_consumer is None:
            return
        try:
            while self._running:
                halt = False
                try:
                    batch = await self.consumer.getmany(timeout_ms=1000, max_records=100)
                    halt = await self._process_consumer_batch(batch)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error in alert consumer loop")
                    await asyncio.sleep(0.5)
                    continue
                if halt:
                    logger.critical(
                        "Halting alert consumer loop after SESSION_FAILED; "
                        "failed record left uncommitted for inspection"
                    )
                    self._running = False
                    break
        except asyncio.CancelledError:
            logger.debug("Alert consumer loop cancelled")
            raise


async def run_alert_service(settings: AlertServiceSettings) -> None:
    metrics = None
    if settings.metrics_port:
        metrics = build_runtime_metrics()
        start_process_metrics(settings.metrics_port, registry=metrics.registry)

    service = AlertService(settings, metrics=metrics)
    await service.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    finally:
        await service.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = AlertServiceSettings.from_env()
    asyncio.run(run_alert_service(settings))


if __name__ == "__main__":
    main()
