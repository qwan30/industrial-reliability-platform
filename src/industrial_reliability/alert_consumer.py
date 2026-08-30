"""Kafka consumer for score decisions and transactional outbox dispatcher for alerts."""

from __future__ import annotations

import asyncio
import enum
import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from industrial_reliability.alert_policy import LockedAlertPolicyV1
from industrial_reliability.alert_state import transition
from industrial_reliability.kafka_io import decode_message, encode_message
from industrial_reliability.metrics import RuntimeMetrics
from industrial_reliability.persistence import RuntimeStore
from industrial_reliability.runtime_messages import (
    QUARANTINE_TOPIC,
    REPLAY_STATUS_TOPIC,
    SCORES_TOPIC,
    QuarantineRecordV1,
    ReplayStatusV1,
    ScoreDecisionV1,
)

logger = logging.getLogger(__name__)


class ProcessOutcome(enum.StrEnum):
    COMMITTED = "COMMITTED"
    SESSION_FAILED = "SESSION_FAILED"
    QUARANTINED = "QUARANTINED"
    SKIPPED = "SKIPPED"


class AlertConsumer:
    def __init__(
        self,
        store: RuntimeStore,
        policy: LockedAlertPolicyV1,
        producer: AIOKafkaProducer | None = None,
        consumer: AIOKafkaConsumer | None = None,
        machine_id: str = "metropt3",
        metrics: RuntimeMetrics | None = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.producer = producer
        self.consumer = consumer
        self.machine_id = machine_id
        self.metrics = metrics
        self._failed_sessions: set[UUID] = set()

    def _assert_identity(self, decision: ScoreDecisionV1) -> None:
        if decision.source_dataset_sha256 != self.policy.source_dataset_sha256:
            raise ValueError(
                f"Source dataset SHA mismatch: expected {self.policy.source_dataset_sha256}, got {decision.source_dataset_sha256}"
            )
        if decision.contract_sha256 != self.policy.contract_sha256:
            raise ValueError(
                f"Contract SHA mismatch: expected {self.policy.contract_sha256}, got {decision.contract_sha256}"
            )
        if decision.model_version != self.policy.model_version:
            raise ValueError(
                f"Model version mismatch: expected {self.policy.model_version}, got {decision.model_version}"
            )

    async def _fail_session(
        self,
        session_id: UUID,
        source_ts: datetime,
        error_code: str,
    ) -> None:
        self._failed_sessions.add(session_id)
        status = ReplayStatusV1(
            message_id=uuid4(),
            replay_session_id=session_id,
            source_dataset_sha256=self.policy.source_dataset_sha256,
            contract_sha256=self.policy.contract_sha256,
            source_timestamp=source_ts,
            emitted_at=datetime.now(UTC),
            state="FAILED",
            last_sequence=0,
            error_code=error_code,
        )
        self.store.record_replay_status(status)
        if self.producer:
            await self.producer.send_and_wait(
                REPLAY_STATUS_TOPIC,
                value=encode_message(status),
                key=str(session_id).encode("ascii"),
            )

    async def _publish_quarantine(
        self,
        record: object,
        raw_bytes: bytes,
        error: Exception,
    ) -> None:
        if self.producer is None:
            raise RuntimeError("Kafka producer is required to quarantine invalid scores")
        payload_hash = hashlib.sha256(raw_bytes).hexdigest()
        quarantine = QuarantineRecordV1(
            message_id=uuid4(),
            replay_session_id=None,
            source_dataset_sha256="0" * 64,
            contract_sha256="0" * 64,
            source_timestamp=datetime(2020, 1, 1),
            emitted_at=datetime.now(UTC),
            original_topic=str(getattr(record, "topic", SCORES_TOPIC)),
            partition=int(getattr(record, "partition", 0)),
            offset=int(getattr(record, "offset", 0)),
            payload_sha256=payload_hash,
            error_code="INVALID_SCORE_PAYLOAD",
            error_detail=str(error)[:1000],
        )
        await self.producer.send_and_wait(
            QUARANTINE_TOPIC,
            value=encode_message(quarantine),
            key=payload_hash.encode("ascii"),
        )

    async def process(self, record: object) -> ProcessOutcome:
        raw_bytes = getattr(record, "value", b"")
        try:
            decision = decode_message(raw_bytes, ScoreDecisionV1)
        except Exception as error:
            logger.exception("Failed to decode score decision")
            await self._publish_quarantine(record, raw_bytes, error)
            return ProcessOutcome.QUARANTINED

        session_id = decision.replay_session_id
        if session_id in self._failed_sessions:
            return ProcessOutcome.SKIPPED

        try:
            self._assert_identity(decision)
        except ValueError:
            logger.exception("Contract mismatch in score decision")
            await self._fail_session(session_id, decision.source_timestamp, "CONTRACT_MISMATCH")
            return ProcessOutcome.SESSION_FAILED

        state = self.store.load_alert_state(session_id, self.machine_id)
        result = transition(state, decision, self.policy)
        self.store.record_decision_transition(decision, result)

        if self.metrics is not None and result.event is not None:
            self.metrics.record_alert_action(result.event.action.lower())
            self.metrics.set_active_alerts(self.store.count_active_alerts())

        return ProcessOutcome.COMMITTED


class AlertOutboxDispatcher:
    def __init__(self, store: RuntimeStore, producer: AIOKafkaProducer) -> None:
        self.store = store
        self.producer = producer
        self._running = False

    async def dispatch_one(self) -> bool:
        row = self.store.next_unpublished_outbox()
        if row is None:
            return False

        payload_bytes = (
            json.dumps(row.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if isinstance(row.payload, dict)
            else row.payload
        )
        await self.producer.send_and_wait(
            row.topic,
            value=payload_bytes,
            key=row.message_key.encode("ascii"),
        )
        self.store.mark_outbox_published(row.message_id)
        return True

    async def run_loop(self, poll_interval: float = 0.5) -> None:
        self._running = True
        while self._running:
            try:
                dispatched = await self.dispatch_one()
                if not dispatched:
                    await asyncio.sleep(poll_interval)
            except Exception:
                logger.exception("Outbox dispatch error")
                await asyncio.sleep(poll_interval)

    def stop(self) -> None:
        self._running = False
