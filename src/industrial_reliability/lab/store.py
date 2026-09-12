"""Persistence store for virtual lab definitions, runs, commands, and events."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from psycopg import IsolationLevel
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from industrial_reliability.lab.contracts import (
    CommandReceipt,
    CommandRequest,
    ControlState,
    EngineCheckpoint,
    LabAlert,
    LabDefinition,
    LabEvent,
    PhysicalState,
    RunSnapshot,
    RunSpec,
    SimulationRun,
    compute_definition_digest,
    validate_lab,
)
from industrial_reliability.report_hashes import canonical_json_bytes

logger = logging.getLogger(__name__)


class LabStoreError(Exception):
    """Base error for lab store operations."""


class LabNotFoundError(LabStoreError):
    """Requested lab does not exist."""


class LabRevisionConflictError(LabStoreError):
    """Optimistic concurrency check failed on lab revision."""


class LabNotRunnableError(LabStoreError):
    """Lab definition has structural validation errors and cannot run."""


class RunNotFoundError(LabStoreError):
    """Requested simulation run does not exist."""


class InvalidRunStateError(LabStoreError):
    """Command cannot be accepted in current run state."""


class CommandRevisionConflictError(LabStoreError):
    """Command expected_control_revision does not match current run control_revision."""


class CommandIdentityConflictError(LabStoreError):
    """Duplicate command ID with different payload hash."""


class LabStore:
    """PostgreSQL-backed store for virtual lab lifecycle."""

    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def save_lab(self, definition: LabDefinition, expected_revision: int) -> LabDefinition:
        """Save a lab definition with optimistic concurrency control."""
        digest = compute_definition_digest(definition)

        with self.pool.connection() as conn, conn.cursor() as cur:
            # Check if lab exists
            cur.execute(
                "SELECT current_revision FROM lab_definitions WHERE lab_id = %s FOR UPDATE",
                (str(definition.lab_id),),
            )
            row = cur.fetchone()

            if row is None:
                # First save: expected_revision must be 0 or 1
                if expected_revision not in (0, 1):
                    raise LabRevisionConflictError(
                        f"Cannot create lab {definition.lab_id} with expected_revision={expected_revision}"
                    )
                new_rev = 1
                cur.execute(
                    """
                    INSERT INTO lab_definitions (lab_id, name, current_revision, created_at)
                    VALUES (%s, %s, %s, now())
                    """,
                    (str(definition.lab_id), definition.name, new_rev),
                )
            else:
                current_rev = row[0]
                if current_rev != expected_revision:
                    raise LabRevisionConflictError(
                        f"Lab revision conflict: current={current_rev}, expected={expected_revision}"
                    )
                new_rev = current_rev + 1
                cur.execute(
                    """
                    UPDATE lab_definitions
                    SET current_revision = %s, name = %s
                    WHERE lab_id = %s
                    """,
                    (new_rev, definition.name, str(definition.lab_id)),
                )

            # Insert revision record
            rev_def = definition.model_copy(update={"revision": new_rev})
            cur.execute(
                """
                INSERT INTO lab_revisions (lab_id, revision, definition, digest, created_at)
                VALUES (%s, %s, %s, %s, now())
                """,
                (
                    str(definition.lab_id),
                    new_rev,
                    json.dumps(rev_def.model_dump(mode="json")),
                    digest,
                ),
            )
            conn.commit()
            return rev_def

    def get_lab(self, lab_id: UUID, revision: int | None = None) -> LabDefinition | None:
        """Retrieve a lab definition at latest or specific revision."""
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            if revision is None:
                cur.execute(
                    """
                    SELECT r.definition
                    FROM lab_definitions d
                    JOIN lab_revisions r ON d.lab_id = r.lab_id AND d.current_revision = r.revision
                    WHERE d.lab_id = %s
                    """,
                    (str(lab_id),),
                )
            else:
                cur.execute(
                    """
                    SELECT definition
                    FROM lab_revisions
                    WHERE lab_id = %s AND revision = %s
                    """,
                    (str(lab_id), revision),
                )
            row = cur.fetchone()
            if not row:
                return None
            data = row["definition"]
            if isinstance(data, str):
                data = json.loads(data)
            return LabDefinition.model_validate(data)

    def list_labs(self, after: UUID | None = None, limit: int = 50) -> tuple[dict[str, Any], ...]:
        """List lab summaries with cursor pagination."""
        capped_limit = min(max(1, limit), 100)
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            if after is not None:
                cur.execute(
                    """
                    SELECT lab_id, name, current_revision, created_at
                    FROM lab_definitions
                    WHERE lab_id > %s
                    ORDER BY lab_id ASC
                    LIMIT %s
                    """,
                    (str(after), capped_limit),
                )
            else:
                cur.execute(
                    """
                    SELECT lab_id, name, current_revision, created_at
                    FROM lab_definitions
                    ORDER BY lab_id ASC
                    LIMIT %s
                    """,
                    (capped_limit,),
                )
            rows = cur.fetchall()
            return tuple(
                {
                    "lab_id": UUID(r["lab_id"]),
                    "name": r["name"],
                    "current_revision": r["current_revision"],
                    "created_at": r["created_at"].isoformat(),
                }
                for r in rows
            )

    def start_run(self, spec: RunSpec, run_id: UUID | None = None) -> SimulationRun:
        """Validate and create a new simulation run row in CREATED status."""
        definition = self.get_lab(spec.lab_id, spec.lab_revision)
        if definition is None:
            raise LabNotFoundError(f"Lab {spec.lab_id} revision {spec.lab_revision} does not exist")

        val_result = validate_lab(definition)
        if not val_result.run_eligible:
            raise LabNotRunnableError(
                f"Lab validation failed: {[e.model_dump() for e in val_result.errors]}"
            )

        assigned_run_id = run_id or uuid4()
        def_digest = compute_definition_digest(definition)
        scene_digest = hashlib.sha256(b"scene-v1").hexdigest()
        profile_digest = hashlib.sha256(b"lab-sensor-robust-v1").hexdigest()
        sampling_digest = hashlib.sha256(b"sampling-1hz-v1").hexdigest()

        # Build initial physical state
        pressures = {}
        for a in definition.assets:
            p = float(a.parameters.get("initial_pressure_pa", 400000.0))
            if a.type == "TANK":
                pressures[f"{a.asset_id}:A"] = p
                pressures[f"{a.asset_id}:B"] = p
            elif a.type == "COMPRESSOR":
                pressures[f"{a.asset_id}:OUT"] = p
            elif a.type == "DEMAND":
                pressures[f"{a.asset_id}:IN"] = p
            elif a.type in ("ISOLATION_VALVE", "CONTROL_VALVE"):
                pressures[f"{a.asset_id}:A"] = p
                pressures[f"{a.asset_id}:B"] = p

        initial_physical = PhysicalState(
            tick=0,
            pressures_pa=pressures,
            flows_kg_s={},
            operating_modes={
                str(a.asset_id): "RUNNING" if a.parameters.get("enabled", True) else "OFF"
                for a in definition.assets
                if a.type == "COMPRESSOR"
            },
        )

        initial_checkpoint = EngineCheckpoint(
            schema_version="lab-checkpoint-v1",
            tick=0,
            physical=initial_physical,
            controls=ControlState(),
            accepted_scanned_sequence=0,
            pending_command_ids=(),
            definition_digest=def_digest,
            profile_digest=profile_digest,
            sampling_digest=sampling_digest,
        )

        run = SimulationRun(
            run_id=assigned_run_id,
            spec=spec,
            status="CREATED",
            definition=definition,
            definition_digest=def_digest,
            scene_digest=scene_digest,
            profile_digest=profile_digest,
            sampling_digest=sampling_digest,
            baseline_id=spec.baseline_id,
            model_version="pneumatic-isothermal-v1",
            dt=0.05,
            epoch="2000-01-01T00:00:00Z",
            profile_id="lab-sensor-robust-v1",
            tick=0,
            control_revision=0,
            event_sequence=0,
        )

        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lab_runs (
                    run_id, lab_id, lab_revision, parent_run_id, baseline_id,
                    max_ticks, model_version, status, seed, speed, tick,
                    control_revision, accepted_sequence, event_sequence, fence,
                    definition_digest, profile_digest, scene_digest, sampling_digest,
                    checkpoint, bytes_recorded, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, now(), now()
                )
                """,
                (
                    str(assigned_run_id),
                    str(spec.lab_id),
                    spec.lab_revision,
                    None,
                    str(spec.baseline_id) if spec.baseline_id else None,
                    spec.max_ticks,
                    run.model_version,
                    run.status,
                    spec.seed,
                    spec.speed,
                    0,
                    0,
                    0,
                    0,
                    0,
                    def_digest,
                    profile_digest,
                    scene_digest,
                    sampling_digest,
                    json.dumps(initial_checkpoint.model_dump(mode="json")),
                    0,
                ),
            )
            conn.commit()

        return run

    def get_run(self, run_id: UUID) -> SimulationRun | None:
        """Fetch SimulationRun by run_id."""
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT r.*, rev.definition
                FROM lab_runs r
                JOIN lab_revisions rev ON r.lab_id = rev.lab_id AND r.lab_revision = rev.revision
                WHERE r.run_id = %s
                """,
                (str(run_id),),
            )
            row = cur.fetchone()
            if not row:
                return None

            def_data = row["definition"]
            if isinstance(def_data, str):
                def_data = json.loads(def_data)
            definition = LabDefinition.model_validate(def_data)

            spec = RunSpec(
                lab_id=UUID(row["lab_id"]),
                lab_revision=row["lab_revision"],
                seed=row["seed"],
                speed=row["speed"],
                max_ticks=row["max_ticks"],
                baseline_id=UUID(row["baseline_id"]) if row["baseline_id"] else None,
            )

            return SimulationRun(
                run_id=UUID(row["run_id"]),
                spec=spec,
                status=row["status"],
                definition=definition,
                definition_digest=row["definition_digest"],
                scene_digest=row["scene_digest"],
                profile_digest=row["profile_digest"],
                sampling_digest=row["sampling_digest"],
                baseline_id=UUID(row["baseline_id"]) if row["baseline_id"] else None,
                model_version=row["model_version"],
                dt=0.05,
                epoch="2000-01-01T00:00:00Z",
                profile_id="lab-sensor-robust-v1",
                tick=row["tick"],
                control_revision=row["control_revision"],
                event_sequence=row["event_sequence"],
            )

    def submit_command(self, run_id: UUID, request: CommandRequest) -> CommandReceipt:
        """Submit an operational command with idempotency and revision gating."""
        req_dict = request.model_dump(mode="json")
        payload_hash = hashlib.sha256(canonical_json_bytes(req_dict)).hexdigest()

        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            # Check for existing command by ID
            cur.execute(
                """
                SELECT * FROM lab_commands
                WHERE run_id = %s AND command_id = %s
                """,
                (str(run_id), str(request.command_id)),
            )
            existing_cmd = cur.fetchone()
            if existing_cmd:
                if existing_cmd["payload_hash"] != payload_hash:
                    raise CommandIdentityConflictError(
                        f"Command {request.command_id} already exists with different payload"
                    )
                return CommandReceipt(
                    command_id=UUID(existing_cmd["command_id"]),
                    status=existing_cmd["status"],
                    accepted_sequence=existing_cmd["accepted_sequence"],
                    effective_tick=existing_cmd["effective_tick"],
                    control_revision=existing_cmd["control_revision"],
                    reason_code=existing_cmd["reason_code"],
                )

            # Lock run row
            cur.execute(
                """
                SELECT status, control_revision, accepted_sequence, tick
                FROM lab_runs
                WHERE run_id = %s
                FOR UPDATE
                """,
                (str(run_id),),
            )
            run_row = cur.fetchone()
            if not run_row:
                raise RunNotFoundError(f"Run {run_id} not found")

            status = run_row["status"]
            if status in ("STOPPED", "COMPLETED", "FAILED"):
                raise InvalidRunStateError(
                    f"Cannot submit command to run in terminal state: {status}"
                )

            current_control_rev = run_row["control_revision"]
            if request.expected_control_revision != current_control_rev:
                raise CommandRevisionConflictError(
                    f"Control revision mismatch: expected {request.expected_control_revision}, actual {current_control_rev}"
                )

            new_control_rev = current_control_rev + 1
            new_accepted_seq = run_row["accepted_sequence"] + 1

            receipt = CommandReceipt(
                command_id=request.command_id,
                status="ACCEPTED",
                accepted_sequence=new_accepted_seq,
                effective_tick=None,
                control_revision=new_control_rev,
                reason_code=None,
            )

            cur.execute(
                """
                INSERT INTO lab_commands (
                    run_id, command_id, payload_hash, accepted_sequence,
                    action, target_id, parameters, status, effective_tick,
                    reason_code, control_revision
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    str(run_id),
                    str(request.command_id),
                    payload_hash,
                    new_accepted_seq,
                    request.action,
                    str(request.target_id) if request.target_id else None,
                    json.dumps(request.parameters),
                    receipt.status,
                    receipt.effective_tick,
                    receipt.reason_code,
                    new_control_rev,
                ),
            )

            cur.execute(
                """
                UPDATE lab_runs
                SET control_revision = %s, accepted_sequence = %s, updated_at = now()
                WHERE run_id = %s
                """,
                (new_control_rev, new_accepted_seq, str(run_id)),
            )

            conn.commit()
            return receipt

    def get_snapshot(self, run_id: UUID) -> RunSnapshot | None:
        """Fetch latest committed RunSnapshot inside a repeatable read transaction."""
        with self.pool.connection() as conn:
            conn.isolation_level = IsolationLevel.REPEATABLE_READ
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT tick, status, control_revision, event_sequence, checkpoint
                    FROM lab_runs
                    WHERE run_id = %s
                    """,
                    (str(run_id),),
                )
                run_row = cur.fetchone()
                if not run_row:
                    return None

                chk_data = run_row["checkpoint"]
                if isinstance(chk_data, str):
                    chk_data = json.loads(chk_data)
                checkpoint = EngineCheckpoint.model_validate(chk_data)

                # Fetch pending command receipts
                cur.execute(
                    """
                    SELECT command_id, status, accepted_sequence, effective_tick,
                           control_revision, reason_code
                    FROM lab_commands
                    WHERE run_id = %s AND status = 'ACCEPTED'
                    ORDER BY accepted_sequence ASC
                    """,
                    (str(run_id),),
                )
                cmd_rows = cur.fetchall()
                pending_cmds = tuple(
                    CommandReceipt(
                        command_id=UUID(r["command_id"]),
                        status=r["status"],
                        accepted_sequence=r["accepted_sequence"],
                        effective_tick=r["effective_tick"],
                        control_revision=r["control_revision"],
                        reason_code=r["reason_code"],
                    )
                    for r in cmd_rows
                )

                # Fetch open alerts
                cur.execute(
                    """
                    SELECT alert_id, run_id, asset_id, sensor_id, origin, kind,
                           state, first_tick, last_tick, resolved_tick, evidence
                    FROM lab_alerts
                    WHERE run_id = %s AND state = 'OPEN'
                    ORDER BY first_tick ASC
                    """,
                    (str(run_id),),
                )
                alert_rows = cur.fetchall()
                alerts = tuple(
                    LabAlert(
                        alert_id=UUID(r["alert_id"]),
                        run_id=UUID(r["run_id"]),
                        asset_id=UUID(r["asset_id"]),
                        sensor_id=UUID(r["sensor_id"]),
                        origin=r["origin"],
                        kind=r["kind"],
                        state=r["state"],
                        first_tick=r["first_tick"],
                        last_tick=r["last_tick"],
                        resolved_tick=r["resolved_tick"],
                    )
                    for r in alert_rows
                )

                return RunSnapshot(
                    run_id=run_id,
                    tick=run_row["tick"],
                    status=run_row["status"],
                    control_revision=run_row["control_revision"],
                    event_sequence=run_row["event_sequence"],
                    physical=checkpoint.physical,
                    observations=(),
                    pending_commands=pending_cmds,
                    alerts=alerts,
                    connection_status="CONNECTED",
                )

    def events_after(self, run_id: UUID, sequence: int, limit: int = 256) -> tuple[LabEvent, ...]:
        """Fetch events strictly after sequence ordered by sequence."""
        capped_limit = min(max(1, limit), 1000)
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT event_id, run_id, sequence, kind, tick, payload
                FROM lab_events
                WHERE run_id = %s AND sequence > %s
                ORDER BY sequence ASC
                LIMIT %s
                """,
                (str(run_id), sequence, capped_limit),
            )
            rows = cur.fetchall()
            return tuple(
                LabEvent(
                    event_id=UUID(r["event_id"]),
                    run_id=UUID(r["run_id"]),
                    sequence=r["sequence"],
                    kind=r["kind"],
                    tick=r["tick"],
                    payload=r["payload"]
                    if isinstance(r["payload"], dict)
                    else json.loads(r["payload"]),
                )
                for r in rows
            )

    def append_history(self, run_id: UUID, tick: int, frame: dict[str, Any]) -> None:
        """Append a 1Hz sampled history frame."""
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lab_history (run_id, tick, frame)
                VALUES (%s, %s, %s)
                ON CONFLICT (run_id, tick) DO NOTHING
                """,
                (str(run_id), tick, json.dumps(frame)),
            )
            conn.commit()

    def get_history(
        self, run_id: UUID, from_tick: int = 0, to_tick: int | None = None, limit: int = 300
    ) -> tuple[dict[str, Any], ...]:
        """Fetch historical frames for playback and investigation."""
        capped_limit = min(max(1, limit), 1000)
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            if to_tick is not None:
                cur.execute(
                    """
                    SELECT tick, frame
                    FROM lab_history
                    WHERE run_id = %s AND tick >= %s AND tick <= %s
                    ORDER BY tick ASC
                    LIMIT %s
                    """,
                    (str(run_id), from_tick, to_tick, capped_limit),
                )
            else:
                cur.execute(
                    """
                    SELECT tick, frame
                    FROM lab_history
                    WHERE run_id = %s AND tick >= %s
                    ORDER BY tick ASC
                    LIMIT %s
                    """,
                    (str(run_id), from_tick, capped_limit),
                )
            rows = cur.fetchall()
            return tuple(
                r["frame"] if isinstance(r["frame"], dict) else json.loads(r["frame"]) for r in rows
            )

    def checkpoint(
        self,
        run_id: UUID,
        fence: int,
        expected_tick: int,
        checkpoint_data: EngineCheckpoint,
        events: tuple[LabEvent, ...],
        outbox_messages: tuple[dict[str, Any], ...] = (),
    ) -> bool:
        """Atomic engine checkpoint with fencing and outbox."""
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE lab_runs
                SET tick = %s,
                    checkpoint = %s,
                    event_sequence = event_sequence + %s,
                    updated_at = now()
                WHERE run_id = %s AND fence = %s AND tick = %s
                RETURNING event_sequence
                """,
                (
                    checkpoint_data.tick,
                    json.dumps(checkpoint_data.model_dump(mode="json")),
                    len(events),
                    str(run_id),
                    fence,
                    expected_tick,
                ),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False

            # Insert events
            for ev in events:
                cur.execute(
                    """
                    INSERT INTO lab_events (run_id, sequence, event_id, kind, tick, payload, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    """,
                    (
                        str(run_id),
                        ev.sequence,
                        str(ev.event_id),
                        ev.kind,
                        ev.tick,
                        json.dumps(ev.payload),
                    ),
                )

            # Insert outbox messages
            for msg in outbox_messages:
                cur.execute(
                    """
                    INSERT INTO lab_outbox (message_id, run_id, sensor_id, tick, topic, payload, published_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL)
                    """,
                    (
                        str(msg["message_id"]),
                        str(run_id),
                        str(msg["sensor_id"]),
                        msg["tick"],
                        msg["topic"],
                        json.dumps(msg["payload"]),
                    ),
                )

            conn.commit()
            return True
