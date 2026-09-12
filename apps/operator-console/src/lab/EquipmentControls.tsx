/**
 * Interactive controls for selected equipment (valves, compressors, demands).
 */

import { useState } from "react";
import type { Asset } from "./types";
import { commandController } from "./commandController";
import { useRunSlice } from "./store";

interface EquipmentControlsProps {
  asset: Asset;
}

export function EquipmentControls({ asset }: EquipmentControlsProps) {
  const { runId, status: runStatus } = useRunSlice();
  const isRunning = runStatus === "RUNNING" || runStatus === "PAUSED";

  // Local requested values before commit
  const [load, setLoad] = useState<number>(() => Number(asset.parameters.load ?? 1.0));
  const [enabled, setEnabled] = useState<boolean>(() => Boolean(asset.parameters.enabled ?? true));
  const [opening, setOpening] = useState<number>(() => Number(asset.parameters.opening ?? 1.0));
  const [loadFactor, setLoadFactor] = useState<number>(() => Number(asset.parameters.load_factor ?? 1.0));
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleCommand = async (action: string, params: Record<string, unknown>) => {
    if (!runId || !isRunning) {
      setStatusMessage("Simulation run must be active to send commands");
      return;
    }

    setStatusMessage("Sending command...");
    try {
      const receipt = await commandController.dispatch(runId, action, asset.asset_id, params);
      setStatusMessage(`Command ${receipt.status} (seq ${receipt.accepted_sequence})`);
    } catch (err: unknown) {
      const error = err as { message?: string };
      setStatusMessage(`Error: ${error.message || "Failed"}`);
    }
  };

  return (
    <div className="property-group equipment-controls-group">
      <div className="group-title">Equipment Actuation</div>

      {asset.type === "COMPRESSOR" && (
        <div className="control-fields">
          <div className="prop-row">
            <span className="prop-label">State</span>
            <button
              type="button"
              className={`btn btn-sm ${enabled ? "btn-primary" : "btn-secondary"}`}
              onClick={() => {
                const nextEnabled = !enabled;
                setEnabled(nextEnabled);
                handleCommand("SET_COMPRESSOR_ENABLED", { enabled: nextEnabled });
              }}
            >
              {enabled ? "RUNNING" : "STOPPED"}
            </button>
          </div>

          <div className="control-slider-box">
            <div className="prop-row">
              <span className="prop-label">Load Setpoint</span>
              <span className="prop-value">{(load * 100).toFixed(0)}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={load}
              onChange={(e) => setLoad(parseFloat(e.target.value))}
              onMouseUp={() => handleCommand("SET_COMPRESSOR_LOAD", { load })}
              onTouchEnd={() => handleCommand("SET_COMPRESSOR_LOAD", { load })}
              className="slider"
            />
          </div>
        </div>
      )}

      {asset.type === "ISOLATION_VALVE" && (
        <div className="control-fields">
          <div className="prop-row">
            <span className="prop-label">Valve Position</span>
            <button
              type="button"
              className={`btn btn-sm ${opening >= 0.5 ? "btn-primary" : "btn-secondary"}`}
              onClick={() => {
                const nextOpening = opening >= 0.5 ? 0.0 : 1.0;
                setOpening(nextOpening);
                handleCommand("SET_VALVE_OPENING", { opening: nextOpening });
              }}
            >
              {opening >= 0.5 ? "OPEN" : "CLOSED"}
            </button>
          </div>
        </div>
      )}

      {asset.type === "CONTROL_VALVE" && (
        <div className="control-fields">
          <div className="control-slider-box">
            <div className="prop-row">
              <span className="prop-label">Modulating Opening</span>
              <span className="prop-value">{(opening * 100).toFixed(0)}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.02"
              value={opening}
              onChange={(e) => setOpening(parseFloat(e.target.value))}
              onMouseUp={() => handleCommand("SET_VALVE_OPENING", { opening })}
              onTouchEnd={() => handleCommand("SET_VALVE_OPENING", { opening })}
              className="slider"
            />
          </div>
        </div>
      )}

      {asset.type === "DEMAND" && (
        <div className="control-fields">
          <div className="control-slider-box">
            <div className="prop-row">
              <span className="prop-label">Demand Load Factor</span>
              <span className="prop-value">{loadFactor.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={loadFactor}
              onChange={(e) => setLoadFactor(parseFloat(e.target.value))}
              onMouseUp={() => handleCommand("SET_LOAD_FACTOR", { load_factor: loadFactor })}
              onTouchEnd={() => handleCommand("SET_LOAD_FACTOR", { load_factor: loadFactor })}
              className="slider"
            />
          </div>
        </div>
      )}

      {statusMessage && <div className="status-feedback-text">{statusMessage}</div>}
    </div>
  );
}
