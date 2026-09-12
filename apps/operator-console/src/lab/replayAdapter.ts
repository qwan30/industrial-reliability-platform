/**
 * Adapter converting legacy MetroPT replay artifacts into unified Virtual Lab view models.
 */

import type { RcaReportV1, TelemetryPayload } from "../types";
import type { RcaViewModel, TelemetrySeriesViewModel } from "./viewModels";

export function adaptRcaReportToViewModel(report: RcaReportV1): RcaViewModel {
  return {
    reportId: report.report_id,
    alertId: report.alert_id,
    status: report.status,
    summary: report.summary,
    observations: report.observations.map((obs) => ({
      claim: obs.claim,
      evidenceIds: [...obs.evidence_ids],
    })),
    uncertainty: [...report.uncertainty],
    nextChecks: [...report.next_checks],
    providerModel: report.provider_model,
  };
}

/**
 * Filter and split telemetry series into continuous chunks where gaps exceed 2x median sample interval.
 */
export function buildContinuousTelemetrySeries(
  events: TelemetryPayload[],
  sensorField: string,
  sensorUnit: string
): TelemetrySeriesViewModel[] {
  if (!events.length) return [];

  const sorted = [...events]
    .filter((e) => e.source_timestamp)
    .sort(
      (a, b) => new Date(a.source_timestamp!).getTime() - new Date(b.source_timestamp!).getTime()
    );

  // Compute median sample interval
  const intervals: number[] = [];
  for (let i = 1; i < sorted.length; i++) {
    const diff = new Date(sorted[i].source_timestamp!).getTime() - new Date(sorted[i - 1].source_timestamp!).getTime();
    if (diff > 0) intervals.push(diff);
  }

  intervals.sort((a, b) => a - b);
  const medianInterval = intervals.length ? intervals[Math.floor(intervals.length / 2)] : 1000;
  const maxAllowedGap = 2.0 * medianInterval;

  const chunks: TelemetrySeriesViewModel[] = [];
  let currentChunk: Array<{ timestamp: string; value: number }> = [];

  for (let i = 0; i < sorted.length; i++) {
    const ev = sorted[i];
    const val = ev[sensorField];
    if (val === undefined || val === null || typeof val !== "number" || isNaN(val)) continue;

    if (currentChunk.length > 0) {
      const prevTime = new Date(currentChunk[currentChunk.length - 1].timestamp).getTime();
      const thisTime = new Date(ev.source_timestamp!).getTime();
      if (thisTime - prevTime > maxAllowedGap) {
        chunks.push({
          name: String(sensorField),
          unit: sensorUnit,
          points: currentChunk,
        });
        currentChunk = [];
      }
    }

    currentChunk.push({
      timestamp: ev.source_timestamp!,
      value: Number(val),
    });
  }

  if (currentChunk.length > 0) {
    chunks.push({
      name: String(sensorField),
      unit: sensorUnit,
      points: currentChunk,
    });
  }

  return chunks;
}
