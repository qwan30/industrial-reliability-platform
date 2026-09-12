"""Domain contracts, validation, and serialization for Industrial Reliability Virtual Lab."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from industrial_reliability.report_hashes import canonical_json_bytes

# Valid Asset Types & Literal Types
AssetType = Literal["COMPRESSOR", "TANK", "ISOLATION_VALVE", "CONTROL_VALVE", "DEMAND"]
PortName = Literal["A", "B", "OUT", "IN"]
SensorKind = Literal["PRESSURE", "FLOW"]
ObservationQuality = Literal["GOOD", "MISSING", "INVALID"]
ObservationUnit = Literal["Pa", "kg/s"]
CommandStatus = Literal["ACCEPTED", "APPLIED", "REJECTED", "FAILED"]
EventKind = Literal["RUN_STATUS", "COMMAND", "OBSERVATION", "ALERT"]
AlertOrigin = Literal["PROCESS_LIMIT", "DATA_QUALITY", "ML"]
AlertKind = Literal["BELOW_LIMIT", "ABOVE_LIMIT", "MISSING", "INVALID", "ANOMALY"]
AlertState = Literal["OPEN", "RESOLVED"]
FaultKind = Literal[
    "LEAK", "VALVE_STUCK", "SENSOR_BIAS", "SENSOR_DROPOUT", "COMPRESSOR_UNAVAILABLE"
]
RunStatus = Literal["CREATED", "RUNNING", "PAUSED", "STOPPED", "COMPLETED", "FAILED"]

VALID_PORTS_BY_ASSET_TYPE: dict[AssetType, tuple[PortName, ...]] = {
    "COMPRESSOR": ("OUT",),
    "TANK": ("A", "B"),
    "ISOLATION_VALVE": ("A", "B"),
    "CONTROL_VALVE": ("A", "B"),
    "DEMAND": ("IN",),
}

DEFAULT_PARAMETERS_BY_ASSET_TYPE: dict[AssetType, dict[str, float | bool]] = {
    "TANK": {
        "volume_m3": 0.5,
        "initial_pressure_pa": 400000.0,
    },
    "COMPRESSOR": {
        "q_nom_kg_s": 0.02,
        "p_max_pa": 900000.0,
        "load": 1.0,
        "enabled": True,
        "initial_pressure_pa": 400000.0,
    },
    "ISOLATION_VALVE": {
        "conductance_kg_s_pa": 2e-7,
        "opening": 1.0,
        "initial_pressure_pa": 400000.0,
    },
    "CONTROL_VALVE": {
        "conductance_kg_s_pa": 2e-7,
        "opening": 1.0,
        "initial_pressure_pa": 400000.0,
    },
    "DEMAND": {
        "conductance_kg_s_pa": 1e-8,
        "load_factor": 1.0,
        "initial_pressure_pa": 400000.0,
    },
}


class PortRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: UUID
    port: PortName


class Asset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: UUID
    type: AssetType
    position_m: tuple[float, float, float]
    rotation_y_rad: float
    parameters: dict[str, float | bool] = Field(default_factory=dict)

    @field_validator("position_m")
    @classmethod
    def validate_position(cls, v: tuple[float, float, float]) -> tuple[float, float, float]:
        if len(v) != 3:
            raise ValueError("position_m must have 3 coordinates (x, y, z)")
        x, y, z = v
        for coord in (x, y, z):
            if not math.isfinite(coord):
                raise ValueError("position_m coordinates must be finite")
        if not (-12.0 <= x <= 12.0):
            raise ValueError(f"position X {x} out of range [-12, 12]")
        if abs(y) > 1e-6:
            raise ValueError(f"position Y must be 0, got {y}")
        if not (-8.0 <= z <= 8.0):
            raise ValueError(f"position Z {z} out of range [-8, 8]")
        return (float(x), 0.0, float(z))

    @field_validator("rotation_y_rad")
    @classmethod
    def validate_rotation(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("rotation_y_rad must be finite")
        return float(v)

    @model_validator(mode="after")
    def validate_parameters(self) -> Asset:
        expected_params = DEFAULT_PARAMETERS_BY_ASSET_TYPE[self.type]
        merged = dict(expected_params)
        merged.update(self.parameters)

        extra_keys = set(self.parameters.keys()) - set(expected_params.keys())
        if extra_keys:
            raise ValueError(
                f"Extra parameter keys not allowed for {self.type}: {sorted(extra_keys)}"
            )

        # Validate bounds
        init_p = merged["initial_pressure_pa"]
        if not (isinstance(init_p, (int, float)) and 101325.0 <= init_p <= 1500000.0):
            raise ValueError(f"initial_pressure_pa {init_p} out of range [101325, 1500000]")

        if self.type == "TANK":
            vol = merged["volume_m3"]
            if not (isinstance(vol, (int, float)) and 0.01 <= vol <= 10.0):
                raise ValueError(f"volume_m3 {vol} out of range [0.01, 10.0]")
        elif self.type == "COMPRESSOR":
            q_nom = merged["q_nom_kg_s"]
            if not (isinstance(q_nom, (int, float)) and 0.001 <= q_nom <= 0.2):
                raise ValueError(f"q_nom_kg_s {q_nom} out of range [0.001, 0.2]")
            p_max = merged["p_max_pa"]
            if not (isinstance(p_max, (int, float)) and 200000.0 <= p_max <= 1500000.0):
                raise ValueError(f"p_max_pa {p_max} out of range [200000, 1500000]")
            load = merged["load"]
            if not (isinstance(load, (int, float)) and 0.0 <= load <= 1.0):
                raise ValueError(f"load {load} out of range [0.0, 1.0]")
            if not isinstance(merged["enabled"], bool):
                raise ValueError("enabled must be a boolean")
        elif self.type == "ISOLATION_VALVE":
            cond = merged["conductance_kg_s_pa"]
            if not (isinstance(cond, (int, float)) and 1e-12 <= cond <= 1e-6):
                raise ValueError(f"conductance_kg_s_pa {cond} out of range [1e-12, 1e-6]")
            op = merged["opening"]
            if op not in (0, 1, 0.0, 1.0):
                raise ValueError(f"isolation valve opening must be 0 or 1, got {op}")
        elif self.type == "CONTROL_VALVE":
            cond = merged["conductance_kg_s_pa"]
            if not (isinstance(cond, (int, float)) and 1e-12 <= cond <= 1e-6):
                raise ValueError(f"conductance_kg_s_pa {cond} out of range [1e-12, 1e-6]")
            op = merged["opening"]
            if not (isinstance(op, (int, float)) and 0.0 <= op <= 1.0):
                raise ValueError(f"control valve opening {op} out of range [0.0, 1.0]")
        elif self.type == "DEMAND":
            cond = merged["conductance_kg_s_pa"]
            if not (isinstance(cond, (int, float)) and 1e-12 <= cond <= 1e-6):
                raise ValueError(f"conductance_kg_s_pa {cond} out of range [1e-12, 1e-6]")
            lf = merged["load_factor"]
            if not (isinstance(lf, (int, float)) and 0.0 <= lf <= 2.0):
                raise ValueError(f"load_factor {lf} out of range [0.0, 2.0]")

        return self


class Pipe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pipe_id: UUID
    from_port: PortRef
    to_port: PortRef
    conductance_kg_s_pa: float = Field(default=2e-7, ge=1e-12, le=1e-6)
    waypoints_m: tuple[tuple[float, float, float], ...] = Field(default_factory=tuple)

    @field_validator("conductance_kg_s_pa")
    @classmethod
    def validate_conductance(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("conductance_kg_s_pa must be finite")
        return float(v)

    @field_validator("waypoints_m")
    @classmethod
    def validate_waypoints(
        cls, v: tuple[tuple[float, float, float], ...]
    ) -> tuple[tuple[float, float, float], ...]:
        if len(v) > 16:
            raise ValueError(f"Maximum 16 waypoints allowed, got {len(v)}")
        clean = []
        for pt in v:
            if len(pt) != 3 or not all(math.isfinite(c) for c in pt):
                raise ValueError("Each waypoint must be 3 finite floats")
            clean.append((float(pt[0]), float(pt[1]), float(pt[2])))
        return tuple(clean)

    @model_validator(mode="after")
    def validate_endpoints(self) -> Pipe:
        if (
            self.from_port.asset_id == self.to_port.asset_id
            and self.from_port.port == self.to_port.port
        ):
            raise ValueError(
                f"Pipe cannot connect a port to itself: {self.from_port.asset_id}:{self.from_port.port}"
            )
        return self


class Sensor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sensor_id: UUID
    kind: SensorKind
    target: PortRef | UUID
    noise_std: float
    alarm_low: float | None = None
    alarm_high: float | None = None

    @field_validator("noise_std")
    @classmethod
    def validate_noise(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0:
            raise ValueError("noise_std must be finite non-negative")
        return float(v)

    @model_validator(mode="after")
    def validate_sensor_rules(self) -> Sensor:
        if self.kind == "PRESSURE":
            if not isinstance(self.target, PortRef):
                raise ValueError("PRESSURE sensor target must be PortRef")
            if not (0.0 <= self.noise_std <= 10000.0):
                raise ValueError(f"PRESSURE noise_std {self.noise_std} out of range [0, 10000]")
            hysteresis = 10000.0
        elif self.kind == "FLOW":
            if not isinstance(self.target, UUID):
                raise ValueError("FLOW sensor target must be a pipe UUID")
            if not (0.0 <= self.noise_std <= 0.01):
                raise ValueError(f"FLOW noise_std {self.noise_std} out of range [0, 0.01]")
            hysteresis = 0.001
        else:
            raise ValueError(f"Unknown sensor kind: {self.kind}")

        if self.alarm_low is not None and not math.isfinite(self.alarm_low):
            raise ValueError("alarm_low must be finite")
        if self.alarm_high is not None and not math.isfinite(self.alarm_high):
            raise ValueError("alarm_high must be finite")
        if (
            self.alarm_low is not None
            and self.alarm_high is not None
            and self.alarm_low + hysteresis >= self.alarm_high - hysteresis
        ):
            raise ValueError(
                f"Alarm bounds invalid: low + hysteresis ({self.alarm_low + hysteresis}) "
                f"must be < high - hysteresis ({self.alarm_high - hysteresis})"
            )

        return self


class SceneBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: str
    asset_digest: str
    type: str
    anchors: dict[str, tuple[float, float, float]]
    lod_distances_m: tuple[float, float] = (12.0, 24.0)


class LabDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "lab-definition-v1"
    lab_id: UUID
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    assets: tuple[Asset, ...] = Field(default_factory=tuple)
    pipes: tuple[Pipe, ...] = Field(default_factory=tuple)
    sensors: tuple[Sensor, ...] = Field(default_factory=tuple)
    scene_revision: str = "scene-v1"


def compute_definition_digest(definition: LabDefinition) -> str:
    """Compute deterministic SHA256 digest of a LabDefinition."""
    data = definition.model_dump(mode="json")
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


class LabValidationError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    asset_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    port_refs: tuple[PortRef, ...] = Field(default_factory=tuple)
    message: str


class LabValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_eligible: bool
    definition_digest: str
    model_version: str = "pneumatic-isothermal-v1"
    errors: tuple[LabValidationError, ...] = Field(default_factory=tuple)


def validate_lab(definition: LabDefinition) -> LabValidationResult:
    """Validate a LabDefinition for run eligibility and structural soundness."""
    errors: list[LabValidationError] = []
    digest = compute_definition_digest(definition)

    if not definition.assets:
        errors.append(
            LabValidationError(
                code="EMPTY_LAB",
                message="Lab contains no equipment/assets.",
            )
        )
        return LabValidationResult(
            run_eligible=False,
            definition_digest=digest,
            errors=tuple(errors),
        )

    # Validate asset IDs uniqueness
    asset_map: dict[UUID, Asset] = {}
    for a in definition.assets:
        if a.asset_id in asset_map:
            errors.append(
                LabValidationError(
                    code="DUPLICATE_ASSET_ID",
                    asset_ids=(a.asset_id,),
                    message=f"Duplicate asset ID: {a.asset_id}",
                )
            )
        asset_map[a.asset_id] = a

    # Validate pipe endpoints and duplicates
    pipe_ids: set[UUID] = set()
    connected_pairs: set[frozenset[tuple[UUID, str]]] = set()

    for p in definition.pipes:
        if p.pipe_id in pipe_ids:
            errors.append(
                LabValidationError(
                    code="DUPLICATE_PIPE_ID",
                    message=f"Duplicate pipe ID: {p.pipe_id}",
                )
            )
        pipe_ids.add(p.pipe_id)

        # Validate from_port
        from_asset = asset_map.get(p.from_port.asset_id)
        if not from_asset:
            errors.append(
                LabValidationError(
                    code="INVALID_PORT_REF",
                    port_refs=(p.from_port,),
                    message=f"Pipe {p.pipe_id} references non-existent asset {p.from_port.asset_id}",
                )
            )
        elif p.from_port.port not in VALID_PORTS_BY_ASSET_TYPE.get(from_asset.type, ()):
            errors.append(
                LabValidationError(
                    code="INVALID_PORT_REF",
                    port_refs=(p.from_port,),
                    message=f"Port {p.from_port.port} does not exist on {from_asset.type}",
                )
            )

        # Validate to_port
        to_asset = asset_map.get(p.to_port.asset_id)
        if not to_asset:
            errors.append(
                LabValidationError(
                    code="INVALID_PORT_REF",
                    port_refs=(p.to_port,),
                    message=f"Pipe {p.pipe_id} references non-existent asset {p.to_port.asset_id}",
                )
            )
        elif p.to_port.port not in VALID_PORTS_BY_ASSET_TYPE.get(to_asset.type, ()):
            errors.append(
                LabValidationError(
                    code="INVALID_PORT_REF",
                    port_refs=(p.to_port,),
                    message=f"Port {p.to_port.port} does not exist on {to_asset.type}",
                )
            )

        # Check self-loops and duplicate connections
        pair_key = frozenset(
            [
                (p.from_port.asset_id, p.from_port.port),
                (p.to_port.asset_id, p.to_port.port),
            ]
        )
        if len(pair_key) == 1:
            errors.append(
                LabValidationError(
                    code="SELF_LOOP_PIPE",
                    port_refs=(p.from_port, p.to_port),
                    message=f"Pipe {p.pipe_id} connects port to itself",
                )
            )
        elif pair_key in connected_pairs:
            errors.append(
                LabValidationError(
                    code="DUPLICATE_PIPE",
                    port_refs=(p.from_port, p.to_port),
                    message=f"Duplicate pipe between same ports: {p.from_port} and {p.to_port}",
                )
            )
        connected_pairs.add(pair_key)

    # Validate sensors
    sensor_ids: set[UUID] = set()
    for s in definition.sensors:
        if s.sensor_id in sensor_ids:
            errors.append(
                LabValidationError(
                    code="DUPLICATE_SENSOR_ID",
                    message=f"Duplicate sensor ID: {s.sensor_id}",
                )
            )
        sensor_ids.add(s.sensor_id)

        if s.kind == "PRESSURE":
            assert isinstance(s.target, PortRef)
            target_asset = asset_map.get(s.target.asset_id)
            if not target_asset:
                errors.append(
                    LabValidationError(
                        code="INVALID_SENSOR_TARGET",
                        port_refs=(s.target,),
                        message=f"Sensor {s.sensor_id} targets non-existent asset {s.target.asset_id}",
                    )
                )
            elif s.target.port not in VALID_PORTS_BY_ASSET_TYPE.get(target_asset.type, ()):
                errors.append(
                    LabValidationError(
                        code="INVALID_SENSOR_TARGET",
                        port_refs=(s.target,),
                        message=f"Sensor {s.sensor_id} targets invalid port {s.target.port} on {target_asset.type}",
                    )
                )
        elif s.kind == "FLOW":
            assert isinstance(s.target, UUID)
            if s.target not in pipe_ids:
                errors.append(
                    LabValidationError(
                        code="INVALID_SENSOR_TARGET",
                        message=f"FLOW sensor {s.sensor_id} targets non-existent pipe {s.target}",
                    )
                )

    run_eligible = len(errors) == 0
    return LabValidationResult(
        run_eligible=run_eligible,
        definition_digest=digest,
        errors=tuple(errors),
    )


class RunSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lab_id: UUID
    lab_revision: int = Field(ge=1)
    seed: int = 42
    speed: Literal[1, 10, 100] = 1
    max_ticks: int | None = Field(default=None, gt=0)
    baseline_id: UUID | None = None


class PhysicalState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tick: int = Field(ge=0)
    pressures_pa: dict[str, float]
    flows_kg_s: dict[str, float]
    operating_modes: dict[str, str] = Field(default_factory=dict)


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    asset_id: UUID
    sensor_id: UUID
    tick: int = Field(ge=0)
    unit: ObservationUnit
    value: float | None
    quality: ObservationQuality
    profile_digest: str
    source_mode: Literal["SIMULATION"] = "SIMULATION"


class CommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: UUID
    expected_control_revision: int = Field(ge=0)
    action: str
    target_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class CommandReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: UUID
    status: CommandStatus
    accepted_sequence: int = Field(ge=0)
    effective_tick: int | None = None
    control_revision: int = Field(ge=0)
    reason_code: str | None = None


class LabEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    run_id: UUID
    sequence: int = Field(ge=0)
    kind: EventKind
    tick: int = Field(ge=0)
    payload: dict[str, Any]


class LabAlert(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alert_id: UUID
    run_id: UUID
    asset_id: UUID
    sensor_id: UUID
    origin: AlertOrigin
    kind: AlertKind
    state: AlertState
    first_tick: int = Field(ge=0)
    last_tick: int = Field(ge=0)
    resolved_tick: int | None = None
    evidence_ids: tuple[UUID, ...] = Field(default_factory=tuple)


class ActiveFault(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_id: UUID
    kind: FaultKind
    port: str | None = None
    values: dict[str, float] = Field(default_factory=dict)


class ControlState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    setpoints: dict[str, dict[str, float | bool]] = Field(default_factory=dict)
    active_faults: tuple[ActiveFault, ...] = Field(default_factory=tuple)


class EngineCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "lab-checkpoint-v1"
    tick: int = Field(ge=0)
    physical: PhysicalState
    controls: ControlState
    accepted_scanned_sequence: int = Field(ge=0)
    pending_command_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    definition_digest: str
    profile_digest: str
    sampling_digest: str


class SimulationRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    spec: RunSpec
    status: RunStatus
    definition: LabDefinition
    definition_digest: str
    scene_digest: str
    profile_digest: str
    sampling_digest: str
    baseline_id: UUID | None = None
    model_version: str = "pneumatic-isothermal-v1"
    dt: float = 0.05
    epoch: str = "2000-01-01T00:00:00Z"
    profile_id: str = "lab-sensor-robust-v1"
    tick: int = 0
    control_revision: int = 0
    event_sequence: int = 0


class RunSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    tick: int = Field(ge=0)
    status: str
    control_revision: int = Field(ge=0)
    event_sequence: int = Field(ge=0)
    physical: PhysicalState
    observations: tuple[Observation, ...] = Field(default_factory=tuple)
    pending_commands: tuple[CommandReceipt, ...] = Field(default_factory=tuple)
    alerts: tuple[LabAlert, ...] = Field(default_factory=tuple)
    connection_status: str = "CONNECTED"
