"""Unit tests for the AlertService background daemon."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiokafka import TopicPartition

from industrial_reliability.alert_consumer import ProcessOutcome
from industrial_reliability.alert_service import (
    AlertService,
    AlertServiceSettings,
)
from industrial_reliability.kafka_io import KafkaSettings
from tests.test_persistence import _make_policy


def test_alert_service_settings_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy = _make_policy()
    policy_file = tmp_path / "alert-policy.json"
    policy_file.write_text(json.dumps(policy.to_dict()), encoding="utf-8")

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("ALERT_POLICY_PATH", str(policy_file))
    monkeypatch.setenv("METRICS_PORT", "9103")
    monkeypatch.setenv("MACHINE_ID", "compressor-01")

    settings = AlertServiceSettings.from_env()
    assert settings.kafka.bootstrap_servers == "localhost:9092"
    assert settings.database_url == "postgresql://user:pass@localhost:5432/test"
    assert settings.policy_path == policy_file
    assert settings.metrics_port == 9103
    assert settings.machine_id == "compressor-01"


def test_alert_service_settings_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        AlertServiceSettings.from_env()


@pytest.mark.asyncio
async def test_alert_service_lifecycle(tmp_path: Path) -> None:
    policy = _make_policy()
    policy_file = tmp_path / "alert-policy.json"
    policy_file.write_text(json.dumps(policy.to_dict()), encoding="utf-8")

    settings = AlertServiceSettings(
        kafka=KafkaSettings(bootstrap_servers="localhost:9092", client_id="test"),
        database_url="sqlite:///:memory:",
        policy_path=policy_file,
    )

    mock_producer = AsyncMock()
    mock_consumer = AsyncMock()

    from prometheus_client import CollectorRegistry

    from industrial_reliability.metrics import build_runtime_metrics

    metrics = build_runtime_metrics(CollectorRegistry())
    service = AlertService(settings, metrics=metrics)

    with (
        patch("industrial_reliability.alert_service.AIOKafkaProducer", return_value=mock_producer),
        patch("industrial_reliability.alert_service.AIOKafkaConsumer", return_value=mock_consumer),
    ):
        await service.start()
        assert service._running is True
        assert service.alert_consumer is not None
        assert service.alert_consumer.metrics is metrics
        mock_producer.start.assert_awaited_once()
        mock_consumer.start.assert_awaited_once()

        await service.stop()
        assert service._running is False
        mock_consumer.stop.assert_awaited_once()
        mock_producer.stop.assert_awaited_once()


def test_alert_service_rejects_tampered_policy(tmp_path: Path) -> None:
    policy = _make_policy()
    policy_dict = policy.to_dict()
    # Tamper with threshold without updating policy_sha256
    policy_dict["threshold"] = 999.0

    policy_file = tmp_path / "tampered-alert-policy.json"
    policy_file.write_text(json.dumps(policy_dict), encoding="utf-8")

    settings = AlertServiceSettings(
        kafka=KafkaSettings(bootstrap_servers="localhost:9092", client_id="test"),
        database_url="sqlite:///:memory:",
        policy_path=policy_file,
    )
    with pytest.raises(ValueError, match="integrity check failed"):
        AlertService(settings)


@pytest.mark.asyncio
async def test_alert_service_does_not_commit_on_session_failed(tmp_path: Path) -> None:
    policy = _make_policy()
    policy_file = tmp_path / "alert-policy.json"
    policy_file.write_text(json.dumps(policy.to_dict()), encoding="utf-8")

    settings = AlertServiceSettings(
        kafka=KafkaSettings(bootstrap_servers="localhost:9092", client_id="test"),
        database_url="sqlite:///:memory:",
        policy_path=policy_file,
    )

    service = AlertService(settings)
    mock_consumer = AsyncMock()
    mock_alert_consumer = AsyncMock()

    service.consumer = mock_consumer
    service.alert_consumer = mock_alert_consumer

    # Simulate getmany returning 1 record, but processing returns SESSION_FAILED
    tp = TopicPartition("irp.scores.v1", 0)
    mock_record = Mock(offset=42)
    poll_count = 0

    async def fake_getmany(**kwargs: Any) -> dict[Any, list[Any]]:
        nonlocal poll_count
        poll_count += 1
        if poll_count > 1:
            raise AssertionError("consumer loop re-polled after SESSION_FAILED")
        return {tp: [mock_record]}

    mock_consumer.getmany.side_effect = fake_getmany
    mock_alert_consumer.process.return_value = ProcessOutcome.SESSION_FAILED

    service._running = True
    await service._run_consumer_loop()

    # Verify alert_consumer processed the record exactly once
    mock_alert_consumer.process.assert_awaited_once_with(mock_record)
    # Verify consumer.commit was NOT called because outcome was SESSION_FAILED
    mock_consumer.commit.assert_not_awaited()
    # Verify the loop halted itself instead of hot-looping on the failed record
    assert poll_count == 1
    assert service._running is False


@pytest.mark.asyncio
async def test_alert_service_commits_ok_records_then_halts_on_session_failed(
    tmp_path: Path,
) -> None:
    policy = _make_policy()
    policy_file = tmp_path / "alert-policy.json"
    policy_file.write_text(json.dumps(policy.to_dict()), encoding="utf-8")

    settings = AlertServiceSettings(
        kafka=KafkaSettings(bootstrap_servers="localhost:9092", client_id="test"),
        database_url="sqlite:///:memory:",
        policy_path=policy_file,
    )

    service = AlertService(settings)
    mock_consumer = AsyncMock()
    mock_alert_consumer = AsyncMock()

    service.consumer = mock_consumer
    service.alert_consumer = mock_alert_consumer

    tp = TopicPartition("irp.scores.v1", 0)
    ok_record = Mock(offset=7)
    failed_record = Mock(offset=8)
    batches = [{tp: [ok_record]}, {tp: [failed_record]}]

    async def fake_getmany(**kwargs: Any) -> dict[Any, list[Any]]:
        if not batches:
            raise AssertionError("consumer loop re-polled after SESSION_FAILED")
        return batches.pop(0)

    mock_consumer.getmany.side_effect = fake_getmany
    mock_alert_consumer.process.side_effect = [
        ProcessOutcome.COMMITTED,
        ProcessOutcome.SESSION_FAILED,
    ]

    service._running = True
    await service._run_consumer_loop()

    # The OK record was committed; the SESSION_FAILED record was not
    mock_consumer.commit.assert_awaited_once_with({tp: 8})
    assert mock_alert_consumer.process.await_count == 2
    assert service._running is False
