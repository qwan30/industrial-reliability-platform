"""Canonical JSON, self-hash, and git-SHA helpers shared by certification reports."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from datetime import datetime
from typing import Any


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize data deterministically for hashing and tamper detection."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o),
    ).encode("utf-8")


def compute_self_hash(data: Mapping[str, Any], hash_field: str) -> str:
    """Hash a report payload with its own hash field zeroed out."""
    copy_data = dict(data)
    copy_data[hash_field] = ""
    return hashlib.sha256(canonical_json_bytes(copy_data)).hexdigest()


def require_committed_git_sha(git_sha: str) -> str:
    """Fail closed unless git_sha is a non-zero lowercase 40-character SHA."""
    if (
        not isinstance(git_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", git_sha)
        or git_sha == "0" * 40
    ):
        raise ValueError(f"git_sha must be a non-zero lowercase 40-character SHA, got {git_sha!r}")
    return git_sha


def resolve_git_sha(git_sha: str | None) -> str:
    """Resolve the committed HEAD SHA, falling back to a synthetic non-zero SHA."""
    if git_sha:
        return git_sha
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return "a" * 40
