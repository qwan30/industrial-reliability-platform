from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

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


def _sample_telemetry_event() -> TelemetryEventV1:
    return TelemetryEventV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        machine_id="compressor-01",
        sequence=1,
        tp2=1.0,
        tp3=2.0,
        h1=3.0,
        dv_pressure=4.0,
        reservoirs=5.0,
        oil_temperature=6.0,
        motor_current=7.0,
        comp=1,
        dv_electric=0,
        towers=1,
        mpg=0,
        lps=1,
        pressure_switch=0,
        oil_level=1,
        caudal_impulses=0,
    )


def test_codec_is_canonical_and_rejects_wrong_schema() -> None:
    message = _sample_telemetry_event()
    encoded1 = encode_message(message)
    encoded2 = encode_message(message)
    assert encoded1 == encoded2

    decoded = decode_message(encoded1, TelemetryEventV1)
    assert decoded.sequence == message.sequence
    assert decoded.message_id == message.message_id

    # Decoding into wrong type must fail
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
