/**
 * Shared view models for RCA reports, telemetry charts, and replay adaptation.
 */

export interface RcaObservationViewModel {
  claim: string;
  evidenceIds: string[];
}

export interface RcaViewModel {
  reportId: string;
  alertId: string;
  status: "COMPLETE" | "UNAVAILABLE";
  summary: string;
  observations: RcaObservationViewModel[];
  uncertainty: string[];
  nextChecks: string[];
  providerModel?: string | null;
}

export interface TelemetrySeriesViewModel {
  name: string;
  unit: string;
  points: Array<{ timestamp: string | number; value: number }>;
}

export interface ReplaySessionViewModel {
  sessionId: string;
  status: string;
  currentTimestamp?: string;
  speed: number;
}
