/**
 * Experiment management panel for fault injection, clearing, and run forking.
 */

import { useState } from "react";
import type { FaultKind } from "./types";
import { useEditorSlice, useRunSlice } from "./store";
import { commandController } from "./commandController";

export function ExperimentPanel() {
  const { lab, mode } = useEditorSlice();
  const { runId, status: runStatus } = useRunSlice();

  const [selectedTargetId, setSelectedTargetId] = useState<string>("");
  const [selectedFaultKind, setSelectedFaultKind] = useState<FaultKind>("LEAK");
  const [leakPort, setLeakPort] = useState<string>("A");
  const [conductance, setConductance] = useState<number>(1e-8);
  const [stuckOpening, setStuckOpening] = useState<number>(0.2);
  const [sensorBias, setSensorBias] = useState<number>(150000.0);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  if ((mode !== "OPERATE" && mode !== "INVESTIGATE") || !lab) return null;

  const handleInject = async () => {
    if (!runId || !selectedTargetId) {
      setStatusMessage("Select a target entity first");
      return;
    }

    const params: Record<string, unknown> = {
      kind: selectedFaultKind,
    };

    if (selectedFaultKind === "LEAK") {
      params.port = leakPort;
      params.values = { conductance_kg_s_pa: conductance };
    } else if (selectedFaultKind === "VALVE_STUCK") {
      params.values = { opening: stuckOpening };
    } else if (selectedFaultKind === "SENSOR_BIAS") {
      params.values = { bias: sensorBias };
    }

    try {
      const receipt = await commandController.dispatch(runId, "INJECT_FAULT", selectedTargetId, params);
      setStatusMessage(`Fault injected: ${receipt.status}`);
    } catch (err: unknown) {
      const error = err as { message?: string };
      setStatusMessage(`Error: ${error.message || "Failed"}`);
    }
  };

  const handleClear = async () => {
    if (!runId || !selectedTargetId) return;
    try {
      const receipt = await commandController.dispatch(runId, "CLEAR_FAULT", selectedTargetId, {
        kind: selectedFaultKind,
      });
      setStatusMessage(`Fault cleared: ${receipt.status}`);
    } catch (err: unknown) {
      const error = err as { message?: string };
      setStatusMessage(`Error: ${error.message || "Failed"}`);
    }
  };

  return (
    <div className="lab-panel lab-experiment-panel">
      <div className="panel-header">
        <span className="panel-title">Experiment Fault Injection</span>
      </div>

      <div className="experiment-content">
        <div className="prop-row">
          <span className="prop-label">Target Entity</span>
          <select
            value={selectedTargetId}
            onChange={(e) => setSelectedTargetId(e.target.value)}
            className="input-select"
          >
            <option value="">-- Choose Target --</option>
            <optgroup label="Equipment">
              {lab.assets.map((a) => (
                <option key={a.asset_id} value={a.asset_id}>
                  {a.type} ({a.asset_id.slice(0, 6)})
                </option>
              ))}
            </optgroup>
            <optgroup label="Sensors">
              {lab.sensors.map((s) => (
                <option key={s.sensor_id} value={s.sensor_id}>
                  {s.kind} SENSOR ({s.sensor_id.slice(0, 6)})
                </option>
              ))}
            </optgroup>
          </select>
        </div>

        <div className="prop-row">
          <span className="prop-label">Fault Mode</span>
          <select
            value={selectedFaultKind}
            onChange={(e) => setSelectedFaultKind(e.target.value as FaultKind)}
            className="input-select"
          >
            <option value="LEAK">LEAK (Gas Escape)</option>
            <option value="VALVE_STUCK">VALVE_STUCK (Actuator Lock)</option>
            <option value="COMPRESSOR_UNAVAILABLE">COMPRESSOR_UNAVAILABLE (Trip/Offline)</option>
            <option value="SENSOR_BIAS">SENSOR_BIAS (Calibration Drift)</option>
            <option value="SENSOR_DROPOUT">SENSOR_DROPOUT (Signal Loss)</option>
          </select>
        </div>

        {selectedFaultKind === "LEAK" && (
          <>
            <div className="prop-row">
              <span className="prop-label">Port</span>
              <select
                value={leakPort}
                onChange={(e) => setLeakPort(e.target.value)}
                className="input-select"
              >
                <option value="A">Port A</option>
                <option value="B">Port B</option>
                <option value="OUT">Port OUT</option>
                <option value="IN">Port IN</option>
              </select>
            </div>
            <div className="prop-row">
              <span className="prop-label">Leak Conductance</span>
              <input
                type="number"
                step="1e-9"
                value={conductance}
                onChange={(e) => setConductance(parseFloat(e.target.value))}
                className="input-text"
              />
            </div>
          </>
        )}

        {selectedFaultKind === "VALVE_STUCK" && (
          <div className="prop-row">
            <span className="prop-label">Locked Opening</span>
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={stuckOpening}
              onChange={(e) => setStuckOpening(parseFloat(e.target.value))}
              className="input-text"
            />
          </div>
        )}

        {selectedFaultKind === "SENSOR_BIAS" && (
          <div className="prop-row">
            <span className="prop-label">Bias Offset</span>
            <input
              type="number"
              value={sensorBias}
              onChange={(e) => setSensorBias(parseFloat(e.target.value))}
              className="input-text"
            />
          </div>
        )}

        <div className="experiment-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleInject}
            disabled={!runId || runStatus === "IDLE" || !selectedTargetId}
          >
            Inject Fault
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={handleClear}
            disabled={!runId || runStatus === "IDLE" || !selectedTargetId}
          >
            Clear
          </button>
        </div>

        {statusMessage && <div className="experiment-status-text">{statusMessage}</div>}
      </div>
    </div>
  );
}
