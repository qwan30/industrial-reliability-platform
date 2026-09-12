"""Integration tests for LabStore using PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from industrial_reliability.lab.catalog import clone_lab_definition, get_reference_lab_definition
from industrial_reliability.lab.contracts import (
    CommandRequest,
    ControlState,
    EngineCheckpoint,
    LabEvent,
    PhysicalState,
    RunSpec,
)
from industrial_reliability.lab.store import (
    CommandIdentityConflictError,
    CommandRevisionConflictError,
    LabRevisionConflictError,
    LabStore,
)
from industrial_reliability.migrations import apply_migrations

TEST_DB_URL = os.environ.get("LAB_DATABASE_URL") or os.environ.get(
    "DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp"
)


@pytest.fixture
def lab_pool() -> ConnectionPool:
    require_live = os.environ.get("REQUIRE_INTEGRATION_SERVICES", "").lower() in ("true", "1")
    try:
        with psycopg.connect(TEST_DB_URL, connect_timeout=1) as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        if require_live:
            raise RuntimeError(
                f"Required integration database unavailable at {TEST_DB_URL}: {e}"
            ) from e
        pytest.skip(f"PostgreSQL unavailable at {TEST_DB_URL}")

    # Apply migrations up to 006
    migrations_dir = Path(__file__).resolve().parents[2] / "db" / "migrations"
    apply_migrations(TEST_DB_URL, migrations_dir)

    pool = ConnectionPool(conninfo=TEST_DB_URL, min_size=1, max_size=4, open=False)
    pool.open()
    yield pool
    pool.close()


@pytest.mark.integration
def test_lab_save_and_concurrency_conflict(lab_pool: ConnectionPool) -> None:
    store = LabStore(lab_pool)
    ref_template = get_reference_lab_definition()
    test_lab = clone_lab_definition(ref_template, uuid4(), "Integration Test Lab")

    # Initial save: rev 1
    saved_v1 = store.save_lab(test_lab, expected_revision=1)
    assert saved_v1.revision == 1

    # First update with expected_revision=1 -> rev 2
    updated_draft = saved_v1.model_copy(update={"name": "Integration Test Lab Rev 2"})
    saved_v2 = store.save_lab(updated_draft, expected_revision=1)
    assert saved_v2.revision == 2

    # Concurrent update with stale expected_revision=1 -> conflict!
    stale_draft = saved_v1.model_copy(update={"name": "Stale Update"})
    with pytest.raises(LabRevisionConflictError):
        store.save_lab(stale_draft, expected_revision=1)


@pytest.mark.integration
def test_run_creation_and_command_lifecycle(lab_pool: ConnectionPool) -> None:
    store = LabStore(lab_pool)
    ref_template = get_reference_lab_definition()
    test_lab = clone_lab_definition(ref_template, uuid4(), "Run Lifecycle Lab")
    saved_lab = store.save_lab(test_lab, expected_revision=1)

    # Start run
    spec = RunSpec(lab_id=saved_lab.lab_id, lab_revision=1, seed=123, speed=1)
    run = store.start_run(spec)
    assert run.status == "CREATED"
    assert run.tick == 0

    # Submit command with valid control revision (expected=0)
    cmd_id = uuid4()
    req = CommandRequest(
        command_id=cmd_id,
        expected_control_revision=0,
        action="SET_COMPRESSOR_LOAD",
        parameters={"load": 0.8},
    )
    receipt = store.submit_command(run.run_id, req)
    assert receipt.status == "ACCEPTED"
    assert receipt.control_revision == 1
    assert receipt.accepted_sequence == 1

    # Idempotent retry with same command_id and payload
    receipt_retry = store.submit_command(run.run_id, req)
    assert receipt_retry.status == "ACCEPTED"
    assert receipt_retry.control_revision == 1

    # Conflict with same command_id but different payload
    req_diff = CommandRequest(
        command_id=cmd_id,
        expected_control_revision=1,
        action="SET_COMPRESSOR_LOAD",
        parameters={"load": 0.5},
    )
    with pytest.raises(CommandIdentityConflictError):
        store.submit_command(run.run_id, req_diff)

    # Stale expected_control_revision -> conflict
    req_stale = CommandRequest(
        command_id=uuid4(),
        expected_control_revision=0,  # current is 1
        action="SET_COMPRESSOR_LOAD",
        parameters={"load": 0.5},
    )
    with pytest.raises(CommandRevisionConflictError):
        store.submit_command(run.run_id, req_stale)


@pytest.mark.integration
def test_checkpoint_and_events(lab_pool: ConnectionPool) -> None:
    store = LabStore(lab_pool)
    ref_template = get_reference_lab_definition()
    test_lab = clone_lab_definition(ref_template, uuid4(), "Checkpoint Lab")
    saved_lab = store.save_lab(test_lab, expected_revision=1)

    spec = RunSpec(lab_id=saved_lab.lab_id, lab_revision=1, seed=456, speed=1)
    run = store.start_run(spec)

    # Checkpoint at tick 2
    chk = EngineCheckpoint(
        schema_version="lab-checkpoint-v1",
        tick=2,
        physical=PhysicalState(tick=2, pressures_pa={}, flows_kg_s={}),
        controls=ControlState(),
        accepted_scanned_sequence=0,
        pending_command_ids=(),
        definition_digest=run.definition_digest,
        profile_digest=run.profile_digest,
        sampling_digest=run.sampling_digest,
    )

    ev = LabEvent(
        event_id=uuid4(),
        run_id=run.run_id,
        sequence=1,
        kind="RUN_STATUS",
        tick=2,
        payload={"status": "RUNNING"},
    )

    success = store.checkpoint(
        run_id=run.run_id,
        fence=0,
        expected_tick=0,
        checkpoint_data=chk,
        events=(ev,),
    )
    assert success is True

    # Stale fence / tick fails
    fail = store.checkpoint(
        run_id=run.run_id,
        fence=0,
        expected_tick=0,  # tick is now 2
        checkpoint_data=chk,
        events=(),
    )
    assert fail is False

    events = store.events_after(run.run_id, sequence=0)
    assert len(events) == 1
    assert events[0].event_id == ev.event_id
