"""Deterministic UUIDv5 generation for runtime message IDs and identities."""

from __future__ import annotations

from uuid import UUID, uuid5

RUNTIME_NAMESPACE = UUID("bc626fb9-7438-5da3-9437-f5b66d34aa52")


def runtime_id(kind: str, replay_session_id: UUID, identity: str) -> UUID:
    if not kind or not identity:
        raise ValueError("kind and identity must be non-empty strings")
    return uuid5(RUNTIME_NAMESPACE, f"{kind}:{replay_session_id}:{identity}")
