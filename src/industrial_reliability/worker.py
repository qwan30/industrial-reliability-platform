"""Async Kafka streaming worker computing online features and calling scoring API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.structs import OffsetAndMetadata

from industrial_reliability.kafka_io import (
    decode_message,
    encode_message,
)
from industrial_reliability.online_features import (
    BuilderResult,
    OnlineFeatureBuilder,
)
from industrial_reliability.phase1b_data import sha256_file
from industrial_reliability.runtime_messages import (
    FEATURES_TOPIC,
    QUARANTINE_TOPIC,
    REPLAY_STATUS_TOPIC,
    SCORES_TOPIC,
    TELEMETRY_TOPIC,
    FeatureVectorV1,
    QuarantineRecordV1,
    ReplayStatusV1,
    TelemetryEventV1,
)
from industrial_reliability.scoring_client import (
    PermanentScoringError,
    RetryableScoringError,
    ScoringClient,
)

logger = logging.getLogger(__name__)
PRODUCER_NOT_STARTED = "Producer not started"


class SessionFailedError(RuntimeError):
    """Raised when a replay session fails due to scoring exhaustion or contract mismatch."""


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    bootstrap_servers: str
    scoring_api_url: str
    model_version: str
    source_dataset_sha256: str
    contract_sha256: str
    feature_names: tuple[str, ...]
    client_id: str = "irp-streaming-worker-v1"
    group_id: str = "irp-streaming-worker-v1"

    @classmethod
    def from_env(cls) -> WorkerSettings:
        servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        if not servers:
            raise ValueError("KAFKA_BOOTSTRAP_SERVERS must be set in the environment")

        scoring_url = os.environ.get("SCORING_API_URL", "").strip()
        if not scoring_url:
            raise ValueError("SCORING_API_URL must be set in the environment")

        pkg_dir_str = os.environ.get("CHAMPION_PACKAGE_DIR", "artifacts/champion").strip()
        pkg_dir = Path(pkg_dir_str).resolve()
        manifest_file = pkg_dir / "manifest.json"
        if not manifest_file.is_file():
            raise ValueError(f"Champion manifest not found at {manifest_file}")

        manifest_sha = sha256_file(manifest_file)
        expected_manifest_sha = os.environ.get("CHAMPION_MANIFEST_SHA256", "").strip()
        if expected_manifest_sha and manifest_sha != expected_manifest_sha:
            raise ValueError(
                f"Champion manifest SHA mismatch: expected {expected_manifest_sha}, got {manifest_sha}"
            )

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        model_version = manifest_data["model_version"]
        source_dataset_sha256 = manifest_data["source_dataset_sha256"]
        contract_sha256 = manifest_data["contract_sha256"]
        feature_names = tuple(manifest_data["feature_names"])

        return cls(
            bootstrap_servers=servers,
            scoring_api_url=scoring_url,
            model_version=model_version,
            source_dataset_sha256=source_dataset_sha256,
            contract_sha256=contract_sha256,
            feature_names=feature_names,
        )


class StreamingWorker:
    def __init__(
        self,
        settings: WorkerSettings,
        scoring_client: ScoringClient | None = None,
    ) -> None:
        self.settings = settings
        self.scoring_client = scoring_client or ScoringClient(
            base_url=settings.scoring_api_url,
            model_version=settings.model_version,
        )
        self.producer: AIOKafkaProducer | None = None
        self.consumer: AIOKafkaConsumer | None = None

        self.builders: dict[UUID, OnlineFeatureBuilder] = {}
        self.terminal_status: dict[UUID, ReplayStatusV1] = {}
        self.last_sequence: dict[UUID, int] = {}
        self.session_offsets: dict[UUID, dict[TopicPartition, OffsetAndMetadata]] = defaultdict(
            dict
        )

        self._running = False
        self._failed_sessions: set[UUID] = set()
        self._blocked_partitions: set[tuple[str, int]] = set()
        self._self_emitted_status_ids: set[UUID] = set()

    async def start(self) -> None:
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.bootstrap_servers,
            client_id=f"{self.settings.client_id}-producer",
            acks="all",
            enable_idempotence=True,
        )
        self.consumer = AIOKafkaConsumer(
            TELEMETRY_TOPIC,
            REPLAY_STATUS_TOPIC,
            bootstrap_servers=self.settings.bootstrap_servers,
            client_id=f"{self.settings.client_id}-consumer",
            group_id=self.settings.group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self.producer.start()
        await self.consumer.start()
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        await self.scoring_client.close()

    async def publish_quarantine(
        self,
        raw_bytes: bytes,
        topic: str,
        partition: int,
        offset: int,
        error_code: str,
        error_detail: str,
    ) -> None:
        if self.producer is None:
            raise RuntimeError(PRODUCER_NOT_STARTED)
        payload_hash = hashlib.sha256(raw_bytes).hexdigest()
        quarantine = QuarantineRecordV1(
            message_id=uuid4(),
            replay_session_id=None,
            source_dataset_sha256="0" * 64,
            contract_sha256="0" * 64,
            source_timestamp=datetime(2020, 1, 1, 0, 0),
            emitted_at=datetime.now(UTC),
            original_topic=topic,
            partition=partition,
            offset=offset,
            payload_sha256=payload_hash,
            error_code=error_code,
            error_detail=error_detail[:1000],
        )
        payload = encode_message(quarantine)
        await self.producer.send_and_wait(
            QUARANTINE_TOPIC, value=payload, key=payload_hash.encode("ascii")
        )

    async def _process_feature(self, feature: FeatureVectorV1) -> None:
        if self.producer is None:
            raise RuntimeError(PRODUCER_NOT_STARTED)

        # 1. Publish feature vector
        feat_bytes = encode_message(feature)
        await self.producer.send_and_wait(
            FEATURES_TOPIC,
            value=feat_bytes,
            key=str(feature.window_id).encode("ascii"),
        )

        # 2. Obtain score decision
        try:
            decision = await self.scoring_client.score(feature)
        except (RetryableScoringError, PermanentScoringError) as err:
            logger.error("Scoring failed for feature %s: %s", feature.window_id, err)
            error_code = (
                "SCORING_RETRY_EXHAUSTED"
                if isinstance(err, RetryableScoringError)
                else "SCORING_CONTRACT_MISMATCH"
            )
            await self._fail_session(
                feature.replay_session_id,
                error_code=error_code,
                last_seq=self.last_sequence.get(feature.replay_session_id, 0),
                source_ts=feature.source_timestamp,
            )
            raise SessionFailedError(f"Session {feature.replay_session_id} failed: {err}") from err

        # 3. Publish score decision
        score_bytes = encode_message(decision)
        await self.producer.send_and_wait(
            SCORES_TOPIC,
            value=score_bytes,
            key=str(decision.decision_id).encode("ascii"),
        )

    async def _fail_session(
        self,
        session_id: UUID,
        error_code: str,
        last_seq: int,
        source_ts: datetime,
    ) -> None:
        self._failed_sessions.add(session_id)
        if self.producer is None:
            return

        msg_id = uuid4()
        self._self_emitted_status_ids.add(msg_id)
        failed_status = ReplayStatusV1(
            message_id=msg_id,
            replay_session_id=session_id,
            source_dataset_sha256=self.settings.source_dataset_sha256,
            contract_sha256=self.settings.contract_sha256,
            source_timestamp=source_ts,
            emitted_at=datetime.now(UTC),
            state="FAILED",
            last_sequence=last_seq,
            error_code=error_code,
        )
        status_bytes = encode_message(failed_status)
        await self.producer.send_and_wait(
            REPLAY_STATUS_TOPIC,
            value=status_bytes,
            key=str(session_id).encode("ascii"),
        )

    async def _complete_session(self, status: ReplayStatusV1) -> None:
        session_id = status.replay_session_id
        if session_id in self._failed_sessions:
            return

        builder = self.builders.get(session_id)
        if builder and not builder.is_complete:
            res: BuilderResult = builder.complete(status.source_timestamp)
            for feature in res.features:
                await self._process_feature(feature)

        # ponytail: session-scoped commits replay more after a crash; persist window checkpoints if long replays make recovery cost unacceptable
        offsets_to_commit = self.session_offsets.get(session_id, {})
        if offsets_to_commit and self.consumer:
            await self.consumer.commit(offsets_to_commit)
            logger.info("Committed offsets for completed session %s", session_id)

    async def _handle_telemetry_record(self, record: object) -> None:
        raw_bytes = getattr(record, "value", b"")
        topic = getattr(record, "topic", TELEMETRY_TOPIC)
        partition = getattr(record, "partition", 0)
        offset = getattr(record, "offset", 0)

        tp = TopicPartition(topic, partition)
        if (topic, partition) in self._blocked_partitions:
            return

        try:
            event = decode_message(raw_bytes, TelemetryEventV1)
        except Exception as err:
            self._blocked_partitions.add((topic, partition))
            await self.publish_quarantine(
                raw_bytes, topic, partition, offset, "INVALID_TELEMETRY_PAYLOAD", str(err)
            )
            return

        session_id = event.replay_session_id
        if session_id in self._failed_sessions:
            return

        # Track offset for session
        self.session_offsets[session_id][tp] = OffsetAndMetadata(offset + 1, "")

        if session_id not in self.builders:
            self.builders[session_id] = OnlineFeatureBuilder(
                replay_session_id=session_id,
                machine_id=event.machine_id,
                source_dataset_sha256=self.settings.source_dataset_sha256,
                contract_sha256=self.settings.contract_sha256,
                feature_names=self.settings.feature_names,
            )

        builder = self.builders[session_id]
        res = builder.push(event)
        self.last_sequence[session_id] = event.sequence

        for feature in res.features:
            await self._process_feature(feature)

        # Check if terminal status barrier is reached
        term = self.terminal_status.get(session_id)
        if term and term.state == "COMPLETED" and term.last_sequence == event.sequence:
            await self._complete_session(term)

    async def _handle_status_record(self, record: object) -> None:
        raw_bytes = getattr(record, "value", b"")
        topic = getattr(record, "topic", REPLAY_STATUS_TOPIC)
        partition = getattr(record, "partition", 0)
        offset = getattr(record, "offset", 0)

        tp = TopicPartition(topic, partition)
        try:
            status = decode_message(raw_bytes, ReplayStatusV1)
        except Exception as err:
            self._blocked_partitions.add((topic, partition))
            await self.publish_quarantine(
                raw_bytes, topic, partition, offset, "INVALID_STATUS_PAYLOAD", str(err)
            )
            return

        session_id = status.replay_session_id
        if status.message_id in self._self_emitted_status_ids:
            return

        self.session_offsets[session_id][tp] = OffsetAndMetadata(offset + 1, "")

        if status.state == "FAILED":
            self._failed_sessions.add(session_id)
            return

        if status.state in ("COMPLETED", "STOPPED"):
            self.terminal_status[session_id] = status
            current_seq = self.last_sequence.get(session_id, 0)
            if status.last_sequence is not None and current_seq >= status.last_sequence:
                await self._complete_session(status)

    async def handle_record(self, record: object) -> None:
        topic = getattr(record, "topic", "")
        if topic == TELEMETRY_TOPIC:
            await self._handle_telemetry_record(record)
        elif topic == REPLAY_STATUS_TOPIC:
            await self._handle_status_record(record)

    async def run(self) -> None:
        await self.start()
        try:
            assert self.consumer is not None
            async for record in self.consumer:
                if not self._running:
                    break
                await self.handle_record(record)
        finally:
            await self.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    settings = WorkerSettings.from_env()
    worker = StreamingWorker(settings)
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
