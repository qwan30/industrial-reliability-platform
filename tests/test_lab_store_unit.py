"""Unit tests for LabStore using mock connection pools."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from industrial_reliability.lab.catalog import get_reference_lab_definition
from industrial_reliability.lab.contracts import (
    CommandRequest,
    ControlState,
    EngineCheckpoint,
    PhysicalState,
    RunSpec,
)
from industrial_reliability.lab.store import (
    CommandIdentityConflictError,
    LabRevisionConflictError,
    LabStore,
)


@pytest.fixture
def mock_store():
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    store = LabStore(mock_pool)
    return store, mock_conn, mock_cur


def test_save_lab_initial(mock_store) -> None:
    store, mock_conn, mock_cur = mock_store
    mock_cur.fetchone.return_value = None  # Lab doesn't exist yet

    ref_lab = get_reference_lab_definition()
    saved = store.save_lab(ref_lab, expected_revision=1)
    assert saved.revision == 1
    mock_conn.commit.assert_called_once()


def test_save_lab_revision_conflict(mock_store) -> None:
    store, _mock_conn, mock_cur = mock_store
    mock_cur.fetchone.return_value = [2]  # Current revision is 2

    ref_lab = get_reference_lab_definition()
    with pytest.raises(LabRevisionConflictError):
        store.save_lab(ref_lab, expected_revision=1)


def test_get_lab_found(mock_store) -> None:
    store, _mock_conn, mock_cur = mock_store
    ref_lab = get_reference_lab_definition()
    mock_cur.fetchone.return_value = {"definition": ref_lab.model_dump(mode="json")}

    fetched = store.get_lab(ref_lab.lab_id)
    assert fetched is not None
    assert fetched.lab_id == ref_lab.lab_id


def test_list_labs(mock_store) -> None:
    store, _mock_conn, mock_cur = mock_store
    from datetime import datetime

    mock_cur.fetchall.return_value = [
        {
            "lab_id": str(uuid4()),
            "name": "Test Lab",
            "current_revision": 1,
            "created_at": datetime.now(UTC),
        }
    ]

    labs = store.list_labs(limit=10)
    assert len(labs) == 1
    assert labs[0]["name"] == "Test Lab"


def test_start_run_and_get_snapshot(mock_store) -> None:
    store, _mock_conn, mock_cur = mock_store
    ref_lab = get_reference_lab_definition()

    # Mock get_lab return
    store.get_lab = MagicMock(return_value=ref_lab)

    spec = RunSpec(lab_id=ref_lab.lab_id, lab_revision=1, seed=42, speed=1)
    run = store.start_run(spec)
    assert run.status == "CREATED"
    assert run.tick == 0

    # Test snapshot retrieval
    chk = EngineCheckpoint(
        schema_version="lab-checkpoint-v1",
        tick=0,
        physical=PhysicalState(tick=0, pressures_pa={}, flows_kg_s={}),
        controls=ControlState(),
        accepted_scanned_sequence=0,
        pending_command_ids=(),
        definition_digest=run.definition_digest,
        profile_digest=run.profile_digest,
        sampling_digest=run.sampling_digest,
    )
    mock_cur.fetchone.return_value = {
        "tick": 0,
        "status": "RUNNING",
        "control_revision": 0,
        "event_sequence": 0,
        "checkpoint": chk.model_dump(mode="json"),
    }
    mock_cur.fetchall.side_effect = [[], []]  # commands, alerts

    snap = store.get_snapshot(run.run_id)
    assert snap is not None
    assert snap.status == "RUNNING"


def test_submit_command_duplicate_id_and_conflict(mock_store) -> None:
    store, _mock_conn, mock_cur = mock_store
    run_id = uuid4()
    cmd_id = uuid4()

    req = CommandRequest(
        command_id=cmd_id,
        expected_control_revision=0,
        action="SET_COMPRESSOR_LOAD",
        parameters={"load": 0.8},
    )

    # 1. Existing command with matching payload hash -> idempotent return
    import hashlib

    from industrial_reliability.report_hashes import canonical_json_bytes

    payload_hash = hashlib.sha256(canonical_json_bytes(req.model_dump(mode="json"))).hexdigest()

    mock_cur.fetchone.return_value = {
        "command_id": str(cmd_id),
        "status": "ACCEPTED",
        "accepted_sequence": 1,
        "effective_tick": None,
        "control_revision": 1,
        "reason_code": None,
        "payload_hash": payload_hash,
    }

    receipt = store.submit_command(run_id, req)
    assert receipt.status == "ACCEPTED"

    # 2. Existing command with DIFFERENT payload hash -> conflict
    mock_cur.fetchone.return_value = {
        "command_id": str(cmd_id),
        "status": "ACCEPTED",
        "accepted_sequence": 1,
        "effective_tick": None,
        "control_revision": 1,
        "reason_code": None,
        "payload_hash": "different_hash" * 2,
    }
    with pytest.raises(CommandIdentityConflictError):
        store.submit_command(run_id, req)
