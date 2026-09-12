"""Simulation execution engine managing loop pacing, command execution, and durable checkpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from industrial_reliability.lab.contracts import (
    ActiveFault,
    ControlState,
    EngineCheckpoint,
    LabEvent,
    PhysicalState,
    SimulationRun,
)
from industrial_reliability.lab.simulation.network import (
    compile_lab,
)
from industrial_reliability.lab.simulation.sensors import observe
from industrial_reliability.lab.simulation.solver import step
from industrial_reliability.lab.store import LabStore

logger = logging.getLogger(__name__)

TOPIC_LAB_OBSERVATIONS = "irp.lab.observations.v1"


class SimulationEngine:
    """Runs physics simulation loops, executes queued commands, and creates durable checkpoints."""

    def __init__(
        self,
        pool: ConnectionPool,
        worker_id: UUID | None = None,
    ) -> None:
        self.pool = pool
        self.worker_id = worker_id or uuid4()
        self.store = LabStore(pool)
        self._running_tasks: dict[UUID, asyncio.Task[None]] = {}
        self._active_leases: dict[UUID, int] = {}  # run_id -> fence

    async def run_once(self, run: SimulationRun) -> bool:
        """Run simulation until completion, pause, or error (used for deterministic test runs)."""
        network = compile_lab(run.definition, dt=run.dt)
        checkpoint = self._load_or_create_checkpoint(run)

        current_physical = checkpoint.physical
        current_controls = checkpoint.controls
        tick = checkpoint.tick

        max_ticks = run.spec.max_ticks or 1000

        while tick < max_ticks:
            # Advance 2 ticks per batch
            batch_size = min(2, max_ticks - tick)
            events: list[LabEvent] = []
            outbox_msgs: list[dict[str, Any]] = []

            for _ in range(batch_size):
                current_physical = step(network, current_physical, current_controls, dt=run.dt)
                tick = current_physical.tick

                # 1Hz observation generation (every 20 ticks)
                if tick % 20 == 0:
                    obs = observe(run, current_physical, current_controls)
                    for o in obs:
                        msg_id = uuid4()
                        outbox_msgs.append(
                            {
                                "message_id": msg_id,
                                "sensor_id": o.sensor_id,
                                "tick": o.tick,
                                "topic": TOPIC_LAB_OBSERVATIONS,
                                "payload": o.model_dump(mode="json"),
                            }
                        )

            # Checkpoint
            new_chk = EngineCheckpoint(
                schema_version="lab-checkpoint-v1",
                tick=tick,
                physical=current_physical,
                controls=current_controls,
                accepted_scanned_sequence=checkpoint.accepted_scanned_sequence,
                pending_command_ids=(),
                definition_digest=run.definition_digest,
                profile_digest=run.profile_digest,
                sampling_digest=run.sampling_digest,
            )

            success = self.store.checkpoint(
                run_id=run.run_id,
                fence=0,
                expected_tick=checkpoint.tick,
                checkpoint_data=new_chk,
                events=tuple(events),
                outbox_messages=tuple(outbox_msgs),
            )
            if not success:
                logger.warning("Failed to checkpoint run %s at tick %d", run.run_id, tick)
                return False

            checkpoint = new_chk

        return True

    def execute_command_in_controls(
        self, controls: ControlState, action: str, target_id: UUID | None, params: dict[str, Any]
    ) -> ControlState:
        """Apply operational command to ControlState."""
        new_setpoints = {k: dict(v) for k, v in controls.setpoints.items()}
        new_faults = list(controls.active_faults)

        if action == "SET_COMPRESSOR_LOAD":
            assert target_id is not None
            sp = new_setpoints.setdefault(str(target_id), {})
            sp["load"] = float(params.get("load", 1.0))
        elif action == "SET_COMPRESSOR_ENABLED":
            assert target_id is not None
            sp = new_setpoints.setdefault(str(target_id), {})
            sp["enabled"] = bool(params.get("enabled", True))
        elif action == "SET_VALVE_OPENING":
            assert target_id is not None
            sp = new_setpoints.setdefault(str(target_id), {})
            sp["opening"] = float(params.get("opening", 1.0))
        elif action == "SET_LOAD_FACTOR":
            assert target_id is not None
            sp = new_setpoints.setdefault(str(target_id), {})
            sp["load_factor"] = float(params.get("load_factor", 1.0))
        elif action == "INJECT_FAULT":
            assert target_id is not None
            kind = params["kind"]
            port = params.get("port")
            # Clear existing same kind on same target
            new_faults = [
                f for f in new_faults if not (f.target_id == target_id and f.kind == kind)
            ]
            new_faults.append(
                ActiveFault(
                    target_id=target_id,
                    kind=kind,
                    port=port,
                    values=params.get("values", {}),
                )
            )
        elif action == "CLEAR_FAULT":
            assert target_id is not None
            kind = params["kind"]
            new_faults = [
                f for f in new_faults if not (f.target_id == target_id and f.kind == kind)
            ]

        return ControlState(
            setpoints=new_setpoints,
            active_faults=tuple(new_faults),
        )

    def _load_or_create_checkpoint(self, run: SimulationRun) -> EngineCheckpoint:
        """Retrieve latest engine checkpoint from DB or create initial."""
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT checkpoint FROM lab_runs WHERE run_id = %s", (str(run.run_id),))
            row = cur.fetchone()
            if row and row["checkpoint"]:
                chk_data = row["checkpoint"]
                if isinstance(chk_data, str):
                    chk_data = json.loads(chk_data)
                return EngineCheckpoint.model_validate(chk_data)

        # Fallback to initial
        pressures = {}
        for a in run.definition.assets:
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
            operating_modes={},
        )
        return EngineCheckpoint(
            schema_version="lab-checkpoint-v1",
            tick=0,
            physical=initial_physical,
            controls=ControlState(),
            accepted_scanned_sequence=0,
            pending_command_ids=(),
            definition_digest=run.definition_digest,
            profile_digest=run.profile_digest,
            sampling_digest=run.sampling_digest,
        )
