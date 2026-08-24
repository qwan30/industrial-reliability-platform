"""Canonical Kafka message serialization, deserialization, and environment settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TypeVar

from pydantic import ValidationError

from industrial_reliability.runtime_messages import FrozenMessage

MessageT = TypeVar("MessageT", bound=FrozenMessage)


class MessageDecodeError(ValueError):
    """Raised when a Kafka message cannot be decoded or validated against the expected schema."""


def encode_message(message: FrozenMessage) -> bytes:
    payload = message.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def decode_message[MessageT: FrozenMessage](
    payload: bytes, message_type: type[MessageT]
) -> MessageT:
    try:
        return message_type.model_validate_json(payload)
    except (UnicodeDecodeError, ValidationError, ValueError) as error:
        raise MessageDecodeError(f"Failed to decode {message_type.__name__}: {error}") from error


@dataclass(frozen=True, slots=True)
class KafkaSettings:
    bootstrap_servers: str
    client_id: str = "industrial-reliability"

    @classmethod
    def from_env(cls) -> KafkaSettings:
        servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        if not servers:
            raise ValueError("KAFKA_BOOTSTRAP_SERVERS must be set in the environment")
        client_id = os.environ.get("KAFKA_CLIENT_ID", "industrial-reliability").strip()
        return cls(bootstrap_servers=servers, client_id=client_id)
