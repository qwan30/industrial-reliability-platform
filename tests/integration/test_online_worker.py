from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from tests.helpers_champion import create_mock_phase1b_champion_run
from tests.helpers_replay import make_sample_replay_command
from tests.test_replay import _create_mock_parquet

from industrial_reliability.champion import ChampionScorer, load_champion
from industrial_reliability.kafka_io import (
    KafkaSettings,
    decode_message,
    encode_message,
)
from industrial_reliability.phase1b_data import sha256_file
from industrial_reliability.replay import ReplaySource
from industrial_reliability.replay_service import ReplayService
from industrial_reliability.runtime_messages import (
    FEATURES_TOPIC,
    REPLAY_COMMANDS_TOPIC,
    SCORES_TOPIC,
    FeatureVectorV1,
    ScoreDecisionV1,
)
from industrial_reliability.worker import StreamingWorker, WorkerSettings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_online_worker_stream_features_and_scores(tmp_path: Path) -> None:
    require_live = os.environ.get("REQUIRE_INTEGRATION_SERVICES", "").lower() in ("true", "1")
    try:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

        producer = AIOKafkaProducer(bootstrap_servers="localhost:29092")
        await asyncio.wait_for(producer.start(), timeout=1.5)
        await producer.stop()
    except Exception as exc:
        if require_live:
            raise RuntimeError(
                f"Required integration Kafka broker unavailable at localhost:29092: {exc}"
            ) from exc
        pytest.skip(f"Kafka broker unavailable at localhost:29092: {exc}")

    # 1. Setup mock data and detector
    pq_path = _create_mock_parquet(tmp_path, n_rows=200)
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    scorer = load_champion(mock_run.package_dir, mock_run.manifest_sha256)
    feature_names = tuple(scorer.feature_names)

    # 2. Start replay service and streaming worker
    kafka_settings = KafkaSettings(bootstrap_servers="localhost:29092")
    source = ReplaySource(
        pq_path,
        expected_contract_sha256="b" * 64,
        expected_source_dataset_sha256="a" * 64,
        expected_output_sha256=sha256_file(pq_path),
    )
    replay_service = ReplayService(kafka_settings, source, enable_pacing=False)

    worker_settings = WorkerSettings(
        bootstrap_servers="localhost:29092",
        scoring_api_url="http://localhost:8000",
        model_version=scorer.model_version,
        source_dataset_sha256=scorer.source_dataset_sha256,
        contract_sha256=scorer.contract_sha256,
        feature_names=feature_names,
    )

    # Direct scorer mock client for in-process test
    class MockDirectClient:
        def __init__(self, sc: ChampionScorer) -> None:
            self.sc = sc

        async def score(self, f: FeatureVectorV1) -> ScoreDecisionV1:
            res = self.sc.score(f)
            return ScoreDecisionV1(
                message_id=uuid4(),
                replay_session_id=f.replay_session_id,
                source_dataset_sha256=f.source_dataset_sha256,
                contract_sha256=f.contract_sha256,
                source_timestamp=f.source_timestamp,
                emitted_at=datetime.now(UTC),
                decision_id=uuid4(),
                window_id=f.window_id,
                model_version=self.sc.model_version,
                score=res.score,
                threshold=res.threshold,
                is_anomaly=res.is_anomaly,
                evidence_vector=res.evidence_vector,
            )

        async def close(self) -> None:
            pass

    worker = StreamingWorker(worker_settings, scoring_client=MockDirectClient(scorer))  # type: ignore[arg-type]

    service_task = asyncio.create_task(replay_service.run())
    worker_task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.5)

    try:
        session_id = uuid4()
        cmd = make_sample_replay_command(
            action="START",
            session_id=session_id,
            speed=1000,
            range_start=datetime(2020, 3, 1, 0, 0, 0),
            range_end=datetime(2020, 3, 1, 0, 35, 0),
            source_dataset_sha256=scorer.source_dataset_sha256,
            contract_sha256=scorer.contract_sha256,
        )

        test_producer = AIOKafkaProducer(bootstrap_servers="localhost:29092")
        await test_producer.start()
        await test_producer.send_and_wait(
            REPLAY_COMMANDS_TOPIC,
            value=encode_message(cmd),
            key=str(cmd.command_id).encode("utf-8"),
        )
        await test_producer.stop()

        consumer = AIOKafkaConsumer(
            FEATURES_TOPIC,
            SCORES_TOPIC,
            bootstrap_servers="localhost:29092",
            group_id=f"test-consumer-{uuid4()}",
            auto_offset_reset="earliest",
        )
        await consumer.start()

        features = []
        scores = []
        try:
            for _ in range(4):
                msg = await asyncio.wait_for(consumer.getone(), timeout=5.0)
                if msg.topic == FEATURES_TOPIC:
                    features.append(decode_message(msg.value, FeatureVectorV1))
                elif msg.topic == SCORES_TOPIC:
                    scores.append(decode_message(msg.value, ScoreDecisionV1))
        except TimeoutError:
            pass
        finally:
            await consumer.stop()

    finally:
        await replay_service.stop()
        await worker.stop()
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(service_task, timeout=2.0)
            await asyncio.wait_for(worker_task, timeout=2.0)
