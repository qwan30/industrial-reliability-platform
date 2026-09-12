/**
 * TypeScript definitions for Industrial Reliability Virtual Lab v2.
 * Synchronized with src/industrial_reliability/lab/contracts.py
 */

export type AssetType =
  | "COMPRESSOR"
  | "TANK"
  | "ISOLATION_VALVE"
  | "CONTROL_VALVE"
  | "DEMAND";

export type PortName = "A" | "B" | "OUT" | "IN";

export interface PortRef {
  asset_id: string;
  port: PortName;
}

export interface Asset {
  asset_id: string;
  type: AssetType;
  position_m: [number, number, number];
  rotation_y_rad: number;
  parameters: Record<string, number | boolean>;
}

export interface Pipe {
  pipe_id: string;
  from_port: PortRef;
  to_port: PortRef;
  conductance_kg_s_pa: number;
  waypoints_m: [number, number, number][];
}

export type SensorKind = "PRESSURE" | "FLOW";
export type ObservationUnit = "Pa" | "kg/s";
export type ObservationQuality = "GOOD" | "MISSING" | "INVALID";

export interface Sensor {
  sensor_id: string;
  kind: SensorKind;
  target: PortRef | string;
  noise_std: number;
  alarm_low?: number | null;
  alarm_high?: number | null;
}

export interface SceneBinding {
  revision: string;
  asset_digest: string;
  type: string;
  anchors: Record<string, [number, number, number]>;
  lod_distances_m: [number, number];
}

export interface LabDefinition {
  schema_version: string;
  lab_id: string;
  revision: number;
  name: string;
  assets: Asset[];
  pipes: Pipe[];
  sensors: Sensor[];
  scene_revision: string;
}

export interface LabValidationError {
  code: string;
  asset_ids: string[];
  port_refs: PortRef[];
  message: string;
}

export interface LabValidationResult {
  run_eligible: boolean;
  definition_digest: string;
  model_version: string;
  errors: LabValidationError[];
}

export type RunSpeed = 1 | 10 | 100;
export type RunStatus =
  | "CREATED"
  | "RUNNING"
  | "PAUSED"
  | "STOPPED"
  | "COMPLETED"
  | "FAILED";

export interface RunSpec {
  lab_id: string;
  lab_revision: number;
  seed: number;
  speed: RunSpeed;
  max_ticks?: number | null;
  baseline_id?: string | null;
}

export interface PhysicalState {
  tick: number;
  pressures_pa: Record<string, number>;
  flows_kg_s: Record<string, number>;
  operating_modes: Record<string, string>;
}

export interface Observation {
  run_id: string;
  asset_id: string;
  sensor_id: string;
  tick: number;
  unit: ObservationUnit;
  value: number | null;
  quality: ObservationQuality;
  profile_digest: string;
  source_mode: "SIMULATION";
}

export interface CommandRequest {
  command_id: string;
  expected_control_revision: number;
  action: string;
  target_id?: string | null;
  parameters: Record<string, unknown>;
}

export type CommandStatus = "ACCEPTED" | "APPLIED" | "REJECTED" | "FAILED";

export interface CommandReceipt {
  command_id: string;
  status: CommandStatus;
  accepted_sequence: number;
  effective_tick?: number | null;
  control_revision: number;
  reason_code?: string | null;
}
export interface LabEvent {
  event_id: string;
  run_id: string;
  sequence: number;
  kind: string;
  tick: number;
  payload: Record<string, unknown>;
}

export type AlertOrigin = "PROCESS_LIMIT" | "DATA_QUALITY" | "ML";
export type AlertKind =
  | "BELOW_LIMIT"
  | "ABOVE_LIMIT"
  | "MISSING"
  | "INVALID"
  | "ANOMALY";
export type AlertState = "OPEN" | "RESOLVED";
export type FaultKind =
  | "LEAK"
  | "VALVE_STUCK"
  | "SENSOR_BIAS"
  | "SENSOR_DROPOUT"
  | "COMPRESSOR_UNAVAILABLE";

export interface LabAlert {
  alert_id: string;
  run_id: string;
  asset_id: string;
  sensor_id: string;
  origin: AlertOrigin;
  kind: AlertKind;
  state: AlertState;
  first_tick: number;
  last_tick: number;
  resolved_tick?: number | null;
  evidence_ids?: string[];
}

export interface RunSnapshot {
  run_id: string;
  tick: number;
  status: string;
  control_revision: number;
  event_sequence: number;
  physical: PhysicalState;
  observations: Observation[];
  pending_commands: CommandReceipt[];
  alerts: LabAlert[];
  connection_status: string;
}

export interface HistoricalFrame {
  tick: number;
  physical: PhysicalState;
  observations?: Observation[];
  alerts?: string[];
}

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: {
    code: string;
    message: string;
    details?: unknown;
  } | null;
}

export interface LabCatalogItem {
  type: AssetType;
  ports: PortName[];
  parameters: Record<string, number | boolean>;
}

export interface LabCatalog {
  catalog_version: string;
  assets: Record<AssetType, LabCatalogItem>;
  supported_models: string[];
  manifest?: Record<string, unknown>;
}
