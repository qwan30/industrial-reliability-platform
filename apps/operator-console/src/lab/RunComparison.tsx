/**
 * Side-by-side simulation run comparison aligned by simulated seconds.
 */

import { useState, useEffect } from "react";
import type { HistoricalFrame } from "./types";
import { useEditorSlice, useRunSlice } from "./store";
import { historyClient } from "./historyClient";

export function RunComparison() {
  const { lab, mode } = useEditorSlice();
  const { runId: currentRunId } = useRunSlice();

  const [runIdA, setRunIdA] = useState<string>("");
  const [runIdB, setRunIdB] = useState<string>("");
  const [selectedSensorId, setSelectedSensorId] = useState<string>("");
  const [framesA, setFramesA] = useState<HistoricalFrame[]>([]);
  const [framesB, setFramesB] = useState<HistoricalFrame[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (currentRunId && !runIdA) {
      setRunIdA(currentRunId);
    }
  }, [currentRunId, runIdA]);

  useEffect(() => {
    if (lab?.sensors.length && !selectedSensorId) {
      setSelectedSensorId(lab.sensors[0].sensor_id);
    }
  }, [lab, selectedSensorId]);

  useEffect(() => {
    async function loadFrames() {
      if (!runIdA) return;
      setLoading(true);
      try {
        const [fa, fb] = await Promise.all([
          historyClient.getFrames(runIdA, 0, undefined, 300),
          runIdB ? historyClient.getFrames(runIdB, 0, undefined, 300) : Promise.resolve([]),
        ]);
        setFramesA(fa);
        setFramesB(fb);
      } catch (err) {
        console.error("Failed to load comparison frames:", err);
      } finally {
        setLoading(false);
      }
    }

    loadFrames();
  }, [runIdA, runIdB]);

  if (mode !== "INVESTIGATE" || !lab) return null;

  const targetSensor = lab.sensors.find((s) => s.sensor_id === selectedSensorId);

  // Collate aligned comparison points by tick (at 20-tick / 1s intervals)
  const maxTick = Math.max(
    framesA.length ? framesA[framesA.length - 1].tick : 0,
    framesB.length ? framesB[framesB.length - 1].tick : 0
  );

  const sampleTicks: number[] = [];
  for (let t = 0; t <= maxTick; t += 20) {
    sampleTicks.push(t);
  }

  return (
    <div className="lab-panel lab-comparison-panel">
      <div className="panel-header">
        <span className="panel-title">Run Comparison</span>
      </div>

      <div className="comparison-content">
        <div className="comparison-selectors">
          <div className="prop-row">
            <span className="prop-label">Run A (Base)</span>
            <input
              type="text"
              value={runIdA}
              onChange={(e) => setRunIdA(e.target.value)}
              placeholder="Run ID UUID"
              className="input-text"
            />
          </div>

          <div className="prop-row">
            <span className="prop-label">Run B (Compare)</span>
            <input
              type="text"
              value={runIdB}
              onChange={(e) => setRunIdB(e.target.value)}
              placeholder="Run ID UUID"
              className="input-text"
            />
          </div>

          <div className="prop-row">
            <span className="prop-label">Instrument</span>
            <select
              value={selectedSensorId}
              onChange={(e) => setSelectedSensorId(e.target.value)}
              className="input-select"
            >
              {lab.sensors.map((s) => (
                <option key={s.sensor_id} value={s.sensor_id}>
                  {s.kind} ({s.sensor_id.slice(0, 8)})
                </option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <div className="comparison-loading">Loading telemetry frames...</div>
        ) : (
          <div className="comparison-table-wrapper">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Time (s)</th>
                  <th>Run A</th>
                  <th>Run B</th>
                  <th>Delta</th>
                </tr>
              </thead>
              <tbody>
                {sampleTicks.slice(0, 15).map((tick) => {
                  const fA = framesA.find((f) => f.tick === tick);
                  const fB = framesB.find((f) => f.tick === tick);

                  const obsA = fA?.observations?.find((o) => o.sensor_id === selectedSensorId);
                  const obsB = fB?.observations?.find((o) => o.sensor_id === selectedSensorId);

                  const valA = obsA?.value;
                  const valB = obsB?.value;

                  const delta =
                    valA !== undefined && valA !== null && valB !== undefined && valB !== null
                      ? valB - valA
                      : null;

                  const formatVal = (v: number | null | undefined) => {
                    if (v === undefined || v === null) return "—";
                    return targetSensor?.kind === "PRESSURE"
                      ? `${((v - 101325) / 100000).toFixed(2)} bar`
                      : `${v.toFixed(4)} kg/s`;
                  };

                  return (
                    <tr key={tick}>
                      <td>{(tick * 0.05).toFixed(1)}s</td>
                      <td>{formatVal(valA)}</td>
                      <td>{formatVal(valB)}</td>
                      <td className={delta !== null && Math.abs(delta) > 1e-4 ? "delta-highlight" : ""}>
                        {delta !== null ? (delta > 0 ? `+${delta.toFixed(2)}` : delta.toFixed(2)) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
