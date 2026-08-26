from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from industrial_reliability.kafka_io import encode_message
from industrial_reliability.phase1b_data import sha256_file
from industrial_reliability.runtime_messages import (
    FEATURES_TOPIC,
    QUARANTINE_TOPIC,
    REPLAY_STATUS_TOPIC,
    SCORES_TOPIC,
    TELEMETRY_TOPIC,
    EvidenceValueV1,
    FeatureVectorV1,
    ReplayStatusV1,
    ScoreDecisionV1,
)
from industrial_reliability.scoring_client import (
    RetryableScoringError,
)
from industrial_reliability.worker import (
    SessionFailedError,
    StreamingWorker,
    WorkerSettings,
)
from tests.helpers_replay import make_sample_telemetry_event

MODEL_VERSION = "champion-statistical-v1"


def _make_mock_decision(feature: FeatureVectorV1) -> ScoreDecisionV1:
    return ScoreDecisionV1(
        message_id=uuid4(),
        replay_session_id=feature.replay_session_id,
        source_dataset_sha256=feature.source_dataset_sha256,
        contract_sha256=feature.contract_sha256,
        source_timestamp=feature.source_timestamp,
        emitted_at=datetime.now(UTC),
        decision_id=uuid4(),
        window_id=feature.window_id,
        model_version=MODEL_VERSION,
        score=0.5,
        threshold=1.0,
        is_anomaly=False,
        evidence_vector=(
            EvidenceValueV1(feature_name="tp2_mean", feature_value=1.23, robust_deviation=0.2),
        ),
    )


class MockKafkaRecord:
    def __init__(
        self,
        topic: str,
        value: bytes,
        partition: int = 0,
        offset: int = 0,
    ) -> None:
        self.topic = topic
        self.value = value
        self.partition = partition
        self.offset = offset


@pytest.fixture
def worker_settings() -> WorkerSettings:
    return WorkerSettings(
        bootstrap_servers="localhost:9092",
        scoring_api_url="http://scoring-api:8000",
        model_version=MODEL_VERSION,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        feature_names=("tp2_mean", "dv_pressure_mean"),
    )


@pytest.mark.asyncio
async def test_offset_commits_only_after_completed_session_outputs_succeed(
    worker_settings: WorkerSettings,
) -> None:
    session_id = uuid4()
    worker = StreamingWorker(worker_settings)

    published_messages: dict[str, list[Any]] = {
        FEATURES_TOPIC: [],
        SCORES_TOPIC: [],
        REPLAY_STATUS_TOPIC: [],
        QUARANTINE_TOPIC: [],
    }

    mock_producer = AsyncMock()

    async def mock_send(topic: str, value: bytes, key: bytes | None = None) -> None:
        published_messages[topic].append((key, value))

    mock_producer.send_and_wait = AsyncMock(side_effect=mock_send)
    worker.producer = mock_producer

    mock_consumer = AsyncMock()
    commits = []
    mock_consumer.commit = AsyncMock(side_effect=lambda offsets: commits.append(offsets))
    worker.consumer = mock_consumer

    mock_scoring = AsyncMock()
    mock_scoring.score = AsyncMock(side_effect=_make_mock_decision)
    worker.scoring_client = mock_scoring

    start_ts = datetime(2020, 3, 1, 4, 0, 0)
    for i in range(180):
        ev = make_sample_telemetry_event(
            sequence=i + 1,
            session_id=session_id,
            source_timestamp=start_ts + timedelta(seconds=10 * i),
        )
        record = MockKafkaRecord(
            topic=TELEMETRY_TOPIC,
            value=encode_message(ev),
            partition=0,
            offset=i,
        )
        await worker.handle_record(record)

    assert len(commits) == 0

    status = ReplayStatusV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=start_ts + timedelta(seconds=10 * 179),
        emitted_at=datetime.now(UTC),
        state="COMPLETED",
        last_sequence=180,
    )
    status_record = MockKafkaRecord(
        topic=REPLAY_STATUS_TOPIC,
        value=encode_message(status),
        partition=0,
        offset=1,
    )
    await worker.handle_record(status_record)

    assert len(commits) == 1
    assert len(published_messages[FEATURES_TOPIC]) > 0
    assert len(published_messages[SCORES_TOPIC]) > 0


@pytest.mark.asyncio
async def test_completed_status_waits_for_last_telemetry_sequence(
    worker_settings: WorkerSettings,
) -> None:
    session_id = uuid4()
    worker = StreamingWorker(worker_settings)
    worker.producer = AsyncMock()
    commits = []
    worker.consumer = AsyncMock()
    worker.consumer.commit = AsyncMock(side_effect=lambda offsets: commits.append(offsets))

    mock_scoring = AsyncMock()
    mock_scoring.score = AsyncMock(side_effect=_make_mock_decision)
    worker.scoring_client = mock_scoring

    start_ts = datetime(2020, 3, 1, 4, 0, 0)

    status = ReplayStatusV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=start_ts + timedelta(seconds=10 * 179),
        emitted_at=datetime.now(UTC),
        state="COMPLETED",
        last_sequence=180,
    )
    status_record = MockKafkaRecord(
        topic=REPLAY_STATUS_TOPIC,
        value=encode_message(status),
        partition=0,
        offset=1,
    )
    await worker.handle_record(status_record)
    assert len(commits) == 0

    for i in range(180):
        ev = make_sample_telemetry_event(
            sequence=i + 1,
            session_id=session_id,
            source_timestamp=start_ts + timedelta(seconds=10 * i),
        )
        record = MockKafkaRecord(
            topic=TELEMETRY_TOPIC,
            value=encode_message(ev),
            partition=0,
            offset=i,
        )
        await worker.handle_record(record)

    assert len(commits) == 1


@pytest.mark.asyncio
async def test_scoring_retry_exhaustion_marks_session_failed_without_commit(
    worker_settings: WorkerSettings,
) -> None:
    session_id = uuid4()
    worker = StreamingWorker(worker_settings)
    published_status = []

    async def mock_send(topic: str, value: bytes, key: bytes | None = None) -> None:
        if topic == REPLAY_STATUS_TOPIC:
            published_status.append(value)

    worker.producer = AsyncMock()
    worker.producer.send_and_wait = AsyncMock(side_effect=mock_send)
    commits = []
    worker.consumer = AsyncMock()
    worker.consumer.commit = AsyncMock(side_effect=lambda offsets: commits.append(offsets))

    mock_scoring = AsyncMock()
    mock_scoring.score = AsyncMock(
        side_effect=RetryableScoringError("Scoring API timeout exhausted")
    )
    worker.scoring_client = mock_scoring

    start_ts = datetime(2020, 3, 1, 4, 0, 0)
    for i in range(200):
        ev = make_sample_telemetry_event(
            sequence=i + 1,
            session_id=session_id,
            source_timestamp=start_ts + timedelta(seconds=10 * i),
        )
        record = MockKafkaRecord(
            topic=TELEMETRY_TOPIC,
            value=encode_message(ev),
            partition=0,
            offset=i,
        )
        try:
            await worker.handle_record(record)
        except SessionFailedError:
            break

    assert len(commits) == 0
    assert len(published_status) > 0


@pytest.mark.asyncio
async def test_invalid_telemetry_or_status_quarantines_without_commit(
    worker_settings: WorkerSettings,
) -> None:
    worker = StreamingWorker(worker_settings)
    quarantine_messages = []

    async def mock_send(topic: str, value: bytes, key: bytes | None = None) -> None:
        if topic == QUARANTINE_TOPIC:
            quarantine_messages.append(value)

    worker.producer = AsyncMock()
    worker.producer.send_and_wait = AsyncMock(side_effect=mock_send)

    # Bad telemetry
    bad_telemetry = MockKafkaRecord(
        topic=TELEMETRY_TOPIC,
        value=b"not_a_valid_json_payload",
        partition=0,
        offset=42,
    )
    await worker.handle_record(bad_telemetry)
    assert len(quarantine_messages) == 1

    # Bad status
    bad_status = MockKafkaRecord(
        topic=REPLAY_STATUS_TOPIC,
        value=b"bad_status_payload",
        partition=0,
        offset=43,
    )
    await worker.handle_record(bad_status)
    assert len(quarantine_messages) == 2


def test_worker_settings_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_data = {
        "model_version": "champion-statistical-v1",
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "feature_names": ["tp2_mean", "dv_pressure_mean"],
    }
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
    manifest_sha = sha256_file(manifest_file)

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("SCORING_API_URL", "http://localhost:8000")
    monkeypatch.setenv("CHAMPION_PACKAGE_DIR", str(tmp_path))
    monkeypatch.setenv("CHAMPION_MANIFEST_SHA256", manifest_sha)

    settings = WorkerSettings.from_env()
    assert settings.bootstrap_servers == "localhost:9092"
    assert settings.model_version == "champion-statistical-v1"
    assert settings.feature_names == ("tp2_mean", "dv_pressure_mean")

    # Missing env checks
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS")
    with pytest.raises(ValueError, match="KAFKA_BOOTSTRAP_SERVERS"):
        WorkerSettings.from_env()


@pytest.mark.asyncio
async def test_streaming_worker_run_lifecycle() -> None:
    settings = WorkerSettings(
        bootstrap_servers="localhost:9092",
        scoring_api_url="http://localhost:8000",
        contract_sha256="a" * 64,
        source_dataset_sha256="b" * 64,
        model_version="champion-statistical-v1",
        feature_names=("tp2_mean",),
    )
    worker = StreamingWorker(settings)
    mock_consumer = AsyncMock()
    mock_producer = AsyncMock()
    mock_scoring = AsyncMock()

    with (
        patch("industrial_reliability.worker.AIOKafkaConsumer", return_value=mock_consumer),
        patch("industrial_reliability.worker.AIOKafkaProducer", return_value=mock_producer),
        patch("industrial_reliability.worker.ScoringClient", return_value=mock_scoring),
    ):
        await worker.start()
        assert worker._running is True
        await worker.stop()
        assert worker._running is False


def test_worker_settings_from_env_research_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.helpers_champion import build_research_candidate_from_mock_run

    mock = build_research_candidate_from_mock_run(tmp_path)

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("SCORING_API_URL", "http://localhost:8000")
    monkeypatch.setenv("SCORING_PACKAGE_DIR", str(mock.package_dir))
    monkeypatch.setenv("SCORING_MANIFEST_SHA256", mock.manifest_sha256)

    # Without ALLOW_RESEARCH_CANDIDATE -> fails
    monkeypatch.delenv("ALLOW_RESEARCH_CANDIDATE", raising=False)
    with pytest.raises(
        ValueError, match="research-only package requires ALLOW_RESEARCH_CANDIDATE=true"
    ):
        WorkerSettings.from_env()

    # Invalid ALLOW_RESEARCH_CANDIDATE -> ValueError
    monkeypatch.setenv("ALLOW_RESEARCH_CANDIDATE", "invalid")
    with pytest.raises(ValueError, match="invalid ALLOW_RESEARCH_CANDIDATE"):
        WorkerSettings.from_env()

    # With ALLOW_RESEARCH_CANDIDATE=true -> succeeds
    monkeypatch.setenv("ALLOW_RESEARCH_CANDIDATE", "true")
    settings = WorkerSettings.from_env()
    assert settings.model_version == "research-candidate-statistical-v1"
