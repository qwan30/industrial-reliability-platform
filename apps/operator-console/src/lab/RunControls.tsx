/**
 * Simulation lifecycle controls (Run, Pause, Resume, Stop, Speed).
 */

import { useState } from "react";
import { useEditorSlice, useRunSlice, labStore } from "./store";
import { createRun, submitCommand } from "./api";
import type { RunSpeed } from "./types";

export function RunControls() {
  const { lab } = useEditorSlice();
  const { runId, status: runStatus, tick, speed } = useRunSlice();
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleStartRun = async () => {
    if (!lab) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await createRun({
        lab_id: lab.lab_id,
        lab_revision: lab.revision,
        seed: 42,
        speed,
      });
      labStore.setRunSnapshot({
        run_id: res.run_id,
        tick: 0,
        status: "RUNNING",
        control_revision: 0,
        event_sequence: 0,
        physical: { tick: 0, pressures_pa: {}, flows_kg_s: {}, operating_modes: {} },
        observations: [],
        pending_commands: [],
        alerts: [],
        connection_status: "CONNECTED",
      });
    } catch (err: unknown) {
      const error = err as { message?: string };
      setErrorMsg(error.message || "Failed to start run");
    } finally {
      setLoading(false);
    }
  };

  const handleLifecycleCommand = async (action: "PAUSE" | "RESUME" | "STOP") => {
    if (!runId) return;
    setLoading(true);
    try {
      await submitCommand(runId, {
        command_id:
          typeof crypto !== "undefined" && crypto.randomUUID
            ? crypto.randomUUID()
            : `cmd-${Date.now()}`,
        expected_control_revision: labStore.getState().run.snapshot?.control_revision ?? 0,
        action,
        parameters: {},
      });
    } catch (err: unknown) {
      const error = err as { message?: string };
      setErrorMsg(error.message || `Failed to ${action}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSpeedChange = (newSpeed: RunSpeed) => {
    labStore.setRunSpeed(newSpeed);
  };

  const simSeconds = (tick * 0.05).toFixed(1);

  return (
    <div className="run-controls-bar">
      <div className="run-status-cluster">
        <span className={`run-badge status-${runStatus.toLowerCase()}`}>{runStatus}</span>
        <span className="sim-time">t = {simSeconds}s</span>
        <span className="sim-tick">(tick {tick})</span>
      </div>

      <div className="action-buttons">
        {runStatus === "IDLE" || runStatus === "STOPPED" ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleStartRun}
            disabled={loading}
          >
            {loading ? "Starting..." : "Start Run"}
          </button>
        ) : runStatus === "RUNNING" ? (
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => handleLifecycleCommand("PAUSE")}
              disabled={loading}
            >
              Pause
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => handleLifecycleCommand("STOP")}
              disabled={loading}
            >
              Stop
            </button>
          </>
        ) : runStatus === "PAUSED" ? (
          <>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => handleLifecycleCommand("RESUME")}
              disabled={loading}
            >
              Resume
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => handleLifecycleCommand("STOP")}
              disabled={loading}
            >
              Stop
            </button>
          </>
        ) : null}
      </div>

      <div className="speed-cluster">
        <span className="speed-label">Speed:</span>
        {([1, 10, 100] as RunSpeed[]).map((s) => (
          <button
            key={s}
            type="button"
            className={`btn-speed ${speed === s ? "active" : ""}`}
            onClick={() => handleSpeedChange(s)}
          >
            {s}x
          </button>
        ))}
      </div>

      {errorMsg && <div className="run-error-badge">{errorMsg}</div>}
    </div>
  );
}
