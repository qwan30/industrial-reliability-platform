"""Unit tests for shared report hashing and git-SHA helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from industrial_reliability import report_hashes
from industrial_reliability.report_hashes import (
    compute_self_hash,
    require_committed_git_sha,
    resolve_git_sha,
)


def test_resolve_git_sha_returns_explicit_value() -> None:
    assert resolve_git_sha("a" * 40) == "a" * 40


def test_resolve_git_sha_resolves_committed_head() -> None:
    with patch.object(
        report_hashes.subprocess,
        "run",
        return_value=Mock(stdout="  " + "b" * 40 + "\n"),
    ):
        assert resolve_git_sha(None) == "b" * 40


def test_resolve_git_sha_fails_closed_when_head_unresolvable() -> None:
    with (
        patch.object(
            report_hashes.subprocess,
            "run",
            side_effect=OSError("not a git repository"),
        ),
        pytest.raises(RuntimeError, match="unable to resolve committed git HEAD"),
    ):
        resolve_git_sha(None)


def test_resolve_git_sha_fails_closed_on_empty_sha() -> None:
    with (
        patch.object(report_hashes.subprocess, "run", return_value=Mock(stdout="   \n")),
        pytest.raises(RuntimeError, match="empty SHA"),
    ):
        resolve_git_sha(None)


@pytest.mark.parametrize("invalid_sha", ["0" * 40, "abc", "G" * 40, "", None])
def test_require_committed_git_sha_rejects_invalid(invalid_sha: object) -> None:
    with pytest.raises(ValueError, match="git_sha"):
        require_committed_git_sha(invalid_sha)  # type: ignore[arg-type]


def test_compute_self_hash_zeroes_hash_field(tmp_path: Path) -> None:
    payload: dict[str, object] = {"a": 1, "b": [1, 2], "report_sha256": ""}
    first = compute_self_hash(payload, "report_sha256")
    payload["report_sha256"] = first
    assert compute_self_hash(payload, "report_sha256") == first
