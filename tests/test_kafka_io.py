from __future__ import annotations

import pytest

from industrial_reliability.kafka_io import (
    KafkaSettings,
    MessageDecodeError,
    decode_message,
    encode_message,
)
from industrial_reliability.runtime_messages import (
    ReplayCommandV1,
    TelemetryEventV1,
)
from tests.helpers_replay import make_sample_telemetry_event


def test_codec_is_canonical_and_rejects_wrong_schema() -> None:
    message = make_sample_telemetry_event()
    encoded1 = encode_message(message)
    encoded2 = encode_message(message)
    assert encoded1 == encoded2

    decoded = decode_message(encoded1, TelemetryEventV1)
    assert decoded.sequence == message.sequence
    assert decoded.message_id == message.message_id

    with pytest.raises(MessageDecodeError):
        decode_message(encoded1, ReplayCommandV1)


def test_kafka_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    settings = KafkaSettings.from_env()
    assert settings.bootstrap_servers == "localhost:9092"
    assert settings.client_id == "industrial-reliability"

    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    with pytest.raises(ValueError, match="KAFKA_BOOTSTRAP_SERVERS"):
        KafkaSettings.from_env()
