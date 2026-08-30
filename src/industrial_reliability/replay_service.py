"""Async Kafka replay service listening for replay commands and streaming telemetry."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from industrial_reliability.kafka_io import (
    KafkaSettings,
    decode_message,
    encode_message,
)
from industrial_reliability.metrics import RuntimeMetrics, start_process_metrics
from industrial_reliability.replay import (
    ReplayController,
    ReplaySource,
    pace_seconds,
)
from industrial_reliability.runtime_ids import runtime_id
from industrial_reliability.runtime_messages import (
    QUARANTINE_TOPIC,
    REPLAY_COMMANDS_TOPIC,
    REPLAY_STATUS_TOPIC,
    TELEMETRY_TOPIC,
    QuarantineRecordV1,
    ReplayCommandV1,
    ReplayStatusV1,
    TelemetryEventV1,
)

logger = logging.getLogger(__name__)
PRODUCER_NOT_STARTED = "Producer not started"


@dataclass
class RunningSession:
    controller: ReplayController
    task: asyncio.Task[None]
    pause_event: asyncio.Event
    stop_event: asyncio.Event


class ReplayService:
    def __init__(
        self,
        settings: KafkaSettings,
        replay_source: ReplaySource,
        enable_pacing: bool = True,
        metrics: RuntimeMetrics | None = None,
    ) -> None:
        self.settings = settings
        self.source = replay_source
        self.enable_pacing = enable_pacing
        self.metrics = metrics
        self.producer: AIOKafkaProducer | None = None
        self.consumer: AIOKafkaConsumer | None = None
        self.active_session: RunningSession | None = None
        self._running = False

    async def start(self) -> None:
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.bootstrap_servers,
            client_id=f"{self.settings.client_id}-producer",
            acks="all",
            enable_idempotence=True,
        )
        self.consumer = AIOKafkaConsumer(
            REPLAY_COMMANDS_TOPIC,
            bootstrap_servers=self.settings.bootstrap_servers,
            client_id=f"{self.settings.client_id}-consumer",
            group_id="irp-replay-producer-v1",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self.producer.start()
        await self.consumer.start()
        if self.metrics is not None:
            self.metrics.set_dependency_ready("kafka", True)
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self.active_session and not self.active_session.task.done():
            self.active_session.stop_event.set()
            self.active_session.pause_event.set()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self.active_session.task, timeout=2.0)

        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def publish_telemetry(self, event: TelemetryEventV1) -> None:
        if self.metrics is not None:
            self.metrics.record_telemetry("accepted")
        if self.producer is None:
            raise RuntimeError(PRODUCER_NOT_STARTED)
        payload = encode_message(event)
        key = event.machine_id.encode("utf-8")
        await self.producer.send_and_wait(TELEMETRY_TOPIC, value=payload, key=key)

    async def publish_status(self, status: ReplayStatusV1) -> None:
        if self.metrics is not None and status.state == "FAILED" and status.error_code:
            self.metrics.record_replay_session_failure(status.error_code)
        if self.producer is None:
            raise RuntimeError(PRODUCER_NOT_STARTED)
        payload = encode_message(status)
        key = str(status.replay_session_id).encode("utf-8")
        await self.producer.send_and_wait(REPLAY_STATUS_TOPIC, value=payload, key=key)

    async def publish_quarantine(self, record: QuarantineRecordV1) -> None:
        if self.metrics is not None:
            self.metrics.record_telemetry("quarantined")
        if self.producer is None:
            raise RuntimeError(PRODUCER_NOT_STARTED)
        payload = encode_message(record)
        key = record.payload_sha256.encode("utf-8")
        await self.producer.send_and_wait(QUARANTINE_TOPIC, value=payload, key=key)

    async def run(self) -> None:
        await self.start()
        try:
            assert self.consumer is not None
            async for record in self.consumer:
                if not self._running:
                    break
                await self.handle_command_record(record)
                await self.consumer.commit()
        finally:
            await self.stop()

    async def handle_command_record(self, record: object) -> None:
        raw_bytes = getattr(record, "value", b"")
        topic = getattr(record, "topic", REPLAY_COMMANDS_TOPIC)
        partition = getattr(record, "partition", 0)
        offset = getattr(record, "offset", 0)

        try:
            command = decode_message(raw_bytes, ReplayCommandV1)
        except Exception as err:
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
                error_code="INVALID_COMMAND_PAYLOAD",
                error_detail=str(err)[:1000],
            )
            await self.publish_quarantine(quarantine)
            return

        await self.handle_command(command)

    async def _handle_start_command(self, command: ReplayCommandV1) -> None:
        if self.active_session and not self.active_session.task.done():
            ctrl = ReplayController.created(
                command.replay_session_id,
                command.source_dataset_sha256,
                command.contract_sha256,
            )
            failed_ctrl = ctrl.mark_failed(
                error_code="REPLAY_ALREADY_ACTIVE",
                last_sequence=0,
                source_timestamp=command.source_timestamp,
            )
            await self.publish_status(failed_ctrl.status())
            return

        if (
            command.source_dataset_sha256 != self.source.identity.source_dataset_sha256
            or command.contract_sha256 != self.source.identity.contract_sha256
        ):
            failed = ReplayController.created(
                command.replay_session_id,
                self.source.identity.source_dataset_sha256,
                self.source.identity.contract_sha256,
            ).mark_failed(
                "REPLAY_SOURCE_IDENTITY_MISMATCH",
                0,
                command.source_timestamp,
            )
            await self.publish_status(failed.status())
            return

        ctrl = ReplayController.created(
            command.replay_session_id,
            command.source_dataset_sha256,
            command.contract_sha256,
        ).apply(command)

        pause_event = asyncio.Event()
        pause_event.set()
        stop_event = asyncio.Event()

        task = asyncio.create_task(
            self._run_replay_session(ctrl, pause_event, stop_event),
            name=f"replay-{command.replay_session_id}",
        )
        self.active_session = RunningSession(
            controller=ctrl,
            task=task,
            pause_event=pause_event,
            stop_event=stop_event,
        )
        await self.publish_status(ctrl.status())

    async def _handle_pause_command(self, command: ReplayCommandV1) -> None:
        if (
            self.active_session
            and self.active_session.controller.session_id == command.replay_session_id
            and not self.active_session.task.done()
        ):
            self.active_session.pause_event.clear()
            ctrl = self.active_session.controller.apply(command)
            self.active_session.controller = ctrl
            await self.publish_status(ctrl.status())

    async def _handle_resume_command(self, command: ReplayCommandV1) -> None:
        if (
            self.active_session
            and self.active_session.controller.session_id == command.replay_session_id
            and not self.active_session.task.done()
        ):
            ctrl = self.active_session.controller.apply(command)
            self.active_session.controller = ctrl
            self.active_session.pause_event.set()
            await self.publish_status(ctrl.status())

    async def _handle_stop_command(self, command: ReplayCommandV1) -> None:
        if (
            self.active_session
            and self.active_session.controller.session_id == command.replay_session_id
            and not self.active_session.task.done()
        ):
            self.active_session.stop_event.set()
            self.active_session.pause_event.set()
            ctrl = self.active_session.controller.apply(command)
            self.active_session.controller = ctrl
            await self.publish_status(ctrl.status())

    async def handle_command(self, command: ReplayCommandV1) -> None:
        if command.action == "START":
            await self._handle_start_command(command)
        elif command.action == "PAUSE":
            await self._handle_pause_command(command)
        elif command.action == "RESUME":
            await self._handle_resume_command(command)
        elif command.action == "STOP":
            await self._handle_stop_command(command)

    async def _run_replay_session(
        self,
        initial_controller: ReplayController,
        pause_event: asyncio.Event,
        stop_event: asyncio.Event,
    ) -> None:
        ctrl = initial_controller
        last_seq = 0
        last_ts = ctrl.range_start or datetime(2020, 1, 1)

        try:
            start_cmd = ReplayCommandV1(
                message_id=uuid4(),
                replay_session_id=ctrl.session_id,
                source_dataset_sha256=ctrl.source_dataset_sha256,
                contract_sha256=ctrl.contract_sha256,
                source_timestamp=ctrl.range_start or datetime(2020, 1, 1),
                emitted_at=datetime.now(UTC),
                command_id=uuid4(),
                action="START",
                speed=ctrl.speed,  # type: ignore[arg-type]
                range_start=ctrl.range_start,
                range_end=ctrl.range_end,
            )

            prev_ts: datetime | None = None
            for event in self.source.iter_events(start_cmd):
                if stop_event.is_set():
                    return

                await pause_event.wait()
                if stop_event.is_set():
                    return

                if self.enable_pacing and prev_ts is not None and event.source_timestamp > prev_ts:
                    delay = pace_seconds(prev_ts, event.source_timestamp, ctrl.speed)
                    if delay > 0:
                        await asyncio.sleep(delay)

                prev_ts = event.source_timestamp
                last_ts = event.source_timestamp
                last_seq = event.sequence

                await self.publish_telemetry(event)

            ctrl = ctrl.mark_completed(last_seq, last_ts)
            await self.publish_status(ctrl.status())

        except Exception as err:
            logger.exception("Replay session failed: %s", err)
            ctrl = ctrl.mark_failed(
                error_code="REPLAY_STREAM_ERROR",
                last_sequence=last_seq,
                source_timestamp=last_ts,
            )
            await self.publish_status(ctrl.status())


def run_certification(
    parquet_path: Path,
    range_start: datetime,
    range_end: datetime,
    speeds: list[int],
    output_dir: Path,
    expected_contract_sha256: str | None = None,
) -> dict[str, object]:
    safe_out = output_dir.resolve()
    safe_out.mkdir(parents=True, exist_ok=True)
    safe_pq = parquet_path.resolve()
    source = ReplaySource(safe_pq, expected_contract_sha256=expected_contract_sha256)
    results: dict[str, object] = {"speeds": speeds, "streams": {}}

    logical_hashes: set[str] = set()

    for speed in speeds:
        session_id = runtime_id(
            "cert-session",
            UUID("00000000-0000-0000-0000-000000000000"),
            f"{range_start.isoformat()}_{range_end.isoformat()}_{speed}",
        )
        cmd = ReplayCommandV1(
            message_id=uuid4(),
            replay_session_id=session_id,
            source_dataset_sha256=source.identity.source_dataset_sha256,
            contract_sha256=source.identity.contract_sha256,
            source_timestamp=range_start,
            emitted_at=datetime.now(UTC),
            command_id=uuid4(),
            action="START",
            speed=speed,  # type: ignore[arg-type]
            range_start=range_start,
            range_end=range_end,
        )
        events = list(source.iter_events(cmd))
        dumped = [event.model_dump(mode="json") for event in events]
        logical_dumped = [
            event.model_dump(mode="json", exclude={"emitted_at", "message_id", "replay_session_id"})
            for event in events
        ]
        logical_hash = hashlib.sha256(
            json.dumps(logical_dumped, sort_keys=True).encode("utf-8")
        ).hexdigest()
        logical_hashes.add(logical_hash)

        results["streams"][str(speed)] = {  # type: ignore[index]
            "event_count": len(events),
            "logical_stream_sha256": logical_hash,
        }
        (safe_out / f"stream_speed_{speed}.json").write_text(
            json.dumps(dumped, indent=2), encoding="utf-8"
        )

    results["streams_identical"] = len(logical_hashes) == 1
    (safe_out / "certification_summary.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Industrial Reliability Replay Service")
    parser.add_argument("--certify-range-start", type=datetime.fromisoformat, required=False)
    parser.add_argument("--certify-range-end", type=datetime.fromisoformat, required=False)
    parser.add_argument("--speeds", type=int, nargs="+", default=[1, 100, 1000])
    parser.add_argument("--output", type=Path, default=Path("artifacts/certification/phase-3"))
    default_parquet = Path(
        os.environ.get(
            "REPLAY_PARQUET_PATH",
            "data/processed/phase1b/metropt3/telemetry.parquet",
        )
    )
    parser.add_argument(
        "--parquet",
        type=Path,
        default=default_parquet,
    )
    args = parser.parse_args()

    if args.certify_range_start and args.certify_range_end:
        print(f"Running Phase 3 replay certification on {args.parquet}...")
        res = run_certification(
            args.parquet.resolve(),
            args.certify_range_start,
            args.certify_range_end,
            args.speeds,
            args.output.resolve(),
        )
        print("Certification results:", json.dumps(res, indent=2))
    else:
        metrics_port = os.environ.get("METRICS_PORT", "").strip()
        metrics = None
        if metrics_port:
            from prometheus_client import CollectorRegistry

            from industrial_reliability.metrics import build_runtime_metrics

            registry = CollectorRegistry()
            metrics = build_runtime_metrics(registry)
            start_process_metrics(int(metrics_port), registry)
            logger.info("Metrics server started on port %s", metrics_port)

        settings = KafkaSettings.from_env()
        source = ReplaySource(args.parquet.resolve())
        service = ReplayService(settings, source, metrics=metrics)
        asyncio.run(service.run())


if __name__ == "__main__":
    main()
