export type ReplayState = 'CREATED' | 'RUNNING' | 'PAUSED' | 'STOPPED' | 'COMPLETED' | 'FAILED';

export interface ReplaySession {
  replay_session_id: string;
  source_dataset_sha256: string;
  contract_sha256: string;
  model_version: string;
  state: ReplayState;
  last_sequence: number | null;
  source_timestamp: string | null;
  error_code: string | null;
  updated_at: string | null;
}

export type AlertState = 'OPEN' | 'RESOLVED';

export interface AlertSummary {
  alert_id: string;
  replay_session_id: string;
  machine_id: string;
  state: AlertState;
  first_detection: string;
  last_detection: string;
  resolved_at: string | null;
  latest_decision_id: string;
  policy_sha256: string;
}

export interface EvidenceItem {
  feature_name: string;
  feature_value: number;
  robust_deviation: number;
}

export interface RcaObservationV1 {
  claim: string;
  evidence_ids: string[];
}

export interface RcaReportV1 {
  schema_version: 'rca-report-v1';
  message_id: string;
  replay_session_id: string;
  source_dataset_sha256: string;
  contract_sha256: string;
  source_timestamp: string;
  emitted_at: string;
  report_id: string;
  alert_id: string;
  status: 'COMPLETE' | 'UNAVAILABLE';
  summary: string;
  observations: RcaObservationV1[];
  uncertainty: string[];
  next_checks: string[];
  evidence_ids: string[];
  evidence_bundle_sha256: string;
  provider_model: string | null;
}

export interface AlertDetail {
  alert: AlertSummary;
  events: Array<Record<string, unknown>>;
  evidence: EvidenceItem[];
  decisions: Array<Record<string, unknown>>;
  rca: RcaReportV1 | null;
}

export interface EvidenceVectorItem {
  feature_name: string;
  feature_value: number;
  robust_deviation: number;
}

export interface ScorePayload {
  score: number;
  threshold: number;
  is_anomaly: boolean;
  source_timestamp?: string;
  evidence_vector?: EvidenceVectorItem[];
}

export interface TelemetryPayload {
  machine_id: string;
  source_timestamp?: string;
  tp2: number;
  tp3: number;
  h1: number;
  oil_temperature: number;
  motor_current: number;
  comp: number;
  towers: number;
  mpg: number;
  [key: string]: unknown;
}

export interface StatusPayload {
  state: ReplayState;
  last_sequence?: number | null;
  source_timestamp?: string;
  error_code?: string | null;
}

export interface SnapshotPayload {
  replay: ReplaySession | null;
  alerts: AlertSummary[];
}

export type ConnectionStatus = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'RECONNECTING';

export interface DependencyHealth {
  api: boolean;
  database: boolean;
}

export interface StartReplayParams {
  range_start: string;
  range_end: string;
  speed: 1 | 100 | 1000;
}
