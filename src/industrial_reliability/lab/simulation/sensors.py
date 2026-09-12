"""Stateless sensor sampling with deterministic Box-Muller noise."""

from __future__ import annotations

import hashlib
import math
from uuid import UUID

from industrial_reliability.lab.contracts import (
    ControlState,
    Observation,
    ObservationQuality,
    ObservationUnit,
    PhysicalState,
    PortRef,
    SimulationRun,
)

TWO_POW_64 = float(1 << 64)


def compute_gaussian_noise(seed: int, sensor_id: UUID, tick: int) -> float:
    """Stateless Box-Muller normal sample generated from SHA256 stream."""
    key = f"{seed}:{sensor_id}:{tick}:noise".encode()
    digest = hashlib.sha256(key).digest()

    n1 = int.from_bytes(digest[0:8], "big")
    n2 = int.from_bytes(digest[8:16], "big")

    u1 = (n1 + 0.5) / TWO_POW_64
    u2 = (n2 + 0.5) / TWO_POW_64

    # Standard normal Box-Muller transform
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def observe(
    run: SimulationRun,
    state: PhysicalState,
    controls: ControlState,
) -> tuple[Observation, ...]:
    """Sample observations from PhysicalState according to sensor definitions and active faults."""
    observations: list[Observation] = []

    # Map active sensor faults
    sensor_faults = {f.target_id: f for f in controls.active_faults}

    for sensor in run.definition.sensors:
        fault = sensor_faults.get(sensor.sensor_id)
        unit: ObservationUnit
        if sensor.kind == "PRESSURE":
            assert isinstance(sensor.target, PortRef)
            # Find node key
            asset = next(
                (a for a in run.definition.assets if a.asset_id == sensor.target.asset_id),
                None,
            )
            if not asset:
                continue

            if asset.type in ("ISOLATION_VALVE", "CONTROL_VALVE"):
                node_key = f"{sensor.target.asset_id}:{sensor.target.port}"
            else:
                node_key = str(sensor.target.asset_id)

            truth = state.pressures_pa.get(node_key)
            unit = "Pa"
        else:
            # FLOW sensor on pipe
            assert isinstance(sensor.target, UUID)
            pipe_key = str(sensor.target)
            truth = state.flows_kg_s.get(pipe_key, 0.0)
            unit = "kg/s"

        if truth is None:
            # Value could not be sampled
            observations.append(
                Observation(
                    run_id=run.run_id,
                    asset_id=sensor.target.asset_id
                    if isinstance(sensor.target, PortRef)
                    else sensor.target,
                    sensor_id=sensor.sensor_id,
                    tick=state.tick,
                    unit=unit,
                    value=None,
                    quality="MISSING",
                    profile_digest=run.profile_digest,
                    source_mode="SIMULATION",
                )
            )
            continue

        # 2. Check for SENSOR_DROPOUT fault
        if fault and fault.kind == "SENSOR_DROPOUT":
            observations.append(
                Observation(
                    run_id=run.run_id,
                    asset_id=sensor.target.asset_id
                    if isinstance(sensor.target, PortRef)
                    else sensor.target,
                    sensor_id=sensor.sensor_id,
                    tick=state.tick,
                    unit=unit,
                    value=None,
                    quality="MISSING",
                    profile_digest=run.profile_digest,
                    source_mode="SIMULATION",
                )
            )
            continue

        # 3. Add noise
        z = compute_gaussian_noise(run.spec.seed, sensor.sensor_id, state.tick)
        measured = truth + sensor.noise_std * z
        # 4. Check for SENSOR_BIAS fault
        if fault and fault.kind == "SENSOR_BIAS":
            bias = float(fault.values.get("bias", 0.0))
            measured += bias

        # 5. Quality check
        quality: ObservationQuality
        if not math.isfinite(measured):
            quality = "INVALID"
            val = None
        elif sensor.kind == "PRESSURE" and measured < 0.0:
            quality = "INVALID"
            val = measured
        else:
            quality = "GOOD"
            val = measured

        target_asset_id = (
            sensor.target.asset_id if isinstance(sensor.target, PortRef) else sensor.target
        )

        observations.append(
            Observation(
                run_id=run.run_id,
                asset_id=target_asset_id,
                sensor_id=sensor.sensor_id,
                tick=state.tick,
                unit=unit,
                value=val,
                quality=quality,
                profile_digest=run.profile_digest,
                source_mode="SIMULATION",
            )
        )

    return tuple(observations)
