from __future__ import annotations

from uuid import UUID

import pytest

from industrial_reliability.runtime_ids import runtime_id


def test_runtime_id_is_stable_and_domain_separated() -> None:
    session = UUID("11111111-1111-1111-1111-111111111111")
    id1 = runtime_id("telemetry", session, "42")
    id2 = runtime_id("telemetry", session, "42")
    assert id1 == id2

    id_window = runtime_id("window", session, "42")
    assert id_window != id1


def test_runtime_id_rejects_empty_inputs() -> None:
    session = UUID("11111111-1111-1111-1111-111111111111")
    with pytest.raises(ValueError, match="non-empty"):
        runtime_id("", session, "42")
    with pytest.raises(ValueError, match="non-empty"):
        runtime_id("telemetry", session, "")
