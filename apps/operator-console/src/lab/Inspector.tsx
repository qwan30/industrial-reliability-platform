/**
 * Right-side Inspector panel for selected asset, pipe, sensor, or lab overview.
 */

import { useEditorSlice, useSelectionSlice, useRunSlice, labStore } from "./store";
import { EquipmentControls } from "./EquipmentControls";

export function Inspector() {
  const { lab } = useEditorSlice();
  const { selectedId, selectedKind, selectedPort } = useSelectionSlice();
  const { telemetry } = useRunSlice();

  if (!lab) return null;

  // Find selected entity
  const selectedAsset = selectedKind === "ASSET" ? lab.assets.find((a) => a.asset_id === selectedId) : null;
  const selectedPipe = selectedKind === "PIPE" ? lab.pipes.find((p) => p.pipe_id === selectedId) : null;
  const selectedSensor = selectedKind === "SENSOR" ? lab.sensors.find((s) => s.sensor_id === selectedId) : null;

  return (
    <div className="lab-panel lab-inspector-panel">
      <div className="panel-header">
        <span className="panel-title">Inspector</span>
        {selectedId && (
          <button
            type="button"
            className="btn-icon"
            onClick={() => labStore.clearSelection()}
            aria-label="Deselect"
          >
            ✕
          </button>
        )}
      </div>

      <div className="inspector-content">
        {selectedAsset && (
          <div className="inspector-entity">
            <div className="entity-header">
              <span className="badge badge-asset">{selectedAsset.type}</span>
              <span className="entity-id">{selectedAsset.asset_id}</span>
            </div>

            <div className="property-group">
              <div className="group-title">Spatial Transform</div>
              <div className="prop-row">
                <span className="prop-label">Position [X, Y, Z]</span>
                <span className="prop-value">
                  {selectedAsset.position_m.map((v) => v.toFixed(2)).join(", ")} m
                </span>
              </div>
              <div className="prop-row">
                <span className="prop-label">Rotation Y</span>
                <span className="prop-value">{(selectedAsset.rotation_y_rad * (180 / Math.PI)).toFixed(0)}°</span>
              </div>
            </div>

            <div className="property-group">
              <div className="group-title">Parameters</div>
              {Object.entries(selectedAsset.parameters).map(([k, v]) => (
                <div key={k} className="prop-row">
                  <span className="prop-label">{k.replace(/_/g, " ")}</span>
                  <span className="prop-value">
                    {typeof v === "boolean" ? (v ? "TRUE" : "FALSE") : typeof v === "number" ? v.toFixed(3) : String(v)}
                  </span>
                </div>
              ))}
            </div>
            <EquipmentControls asset={selectedAsset} />

            {selectedPort && (
              <div className="property-group">
                <div className="group-title">Selected Port: {selectedPort}</div>
                <p className="port-desc">
                  Port {selectedPort} on {selectedAsset.type}
                </p>
              </div>
            )}
          </div>
        )}

        {selectedPipe && (
          <div className="inspector-entity">
            <div className="entity-header">
              <span className="badge badge-pipe">PIPE</span>
              <span className="entity-id">{selectedPipe.pipe_id}</span>
            </div>

            <div className="property-group">
              <div className="group-title">Endpoints</div>
              <div className="prop-row">
                <span className="prop-label">From Port</span>
                <span className="prop-value">
                  {selectedPipe.from_port.port} ({selectedPipe.from_port.asset_id.slice(0, 8)})
                </span>
              </div>
              <div className="prop-row">
                <span className="prop-label">To Port</span>
                <span className="prop-value">
                  {selectedPipe.to_port.port} ({selectedPipe.to_port.asset_id.slice(0, 8)})
                </span>
              </div>
              <div className="prop-row">
                <span className="prop-label">Conductance</span>
                <span className="prop-value">{selectedPipe.conductance_kg_s_pa.toExponential(2)} kg/(s·Pa)</span>
              </div>
            </div>
          </div>
        )}

        {selectedSensor && (
          <div className="inspector-entity">
            <div className="entity-header">
              <span className={`badge badge-${selectedSensor.kind.toLowerCase()}`}>
                {selectedSensor.kind} SENSOR
              </span>
              <span className="entity-id">{selectedSensor.sensor_id}</span>
            </div>

            <div className="property-group">
              <div className="group-title">Live Telemetry</div>
              <div className="telemetry-box">
                <div className="telemetry-value">
                  {telemetry[selectedSensor.sensor_id] !== undefined ? (
                    selectedSensor.kind === "PRESSURE" ? (
                      `${((telemetry[selectedSensor.sensor_id] - 101325) / 100000).toFixed(2)} bar`
                    ) : (
                      `${telemetry[selectedSensor.sensor_id].toFixed(4)} kg/s`
                    )
                  ) : (
                    <span className="text-muted">NO TELEMETRY</span>
                  )}
                </div>
                <div className="telemetry-unit">
                  {selectedSensor.kind === "PRESSURE" ? "Gauge Pressure (bar)" : "Mass Flow Rate (kg/s)"}
                </div>
              </div>

              <div className="prop-row">
                <span className="prop-label">Alarm Range</span>
                <span className="prop-value">
                  [{selectedSensor.alarm_low ?? "None"}, {selectedSensor.alarm_high ?? "None"}]
                </span>
              </div>
              <div className="prop-row">
                <span className="prop-label">Noise Std</span>
                <span className="prop-value">{selectedSensor.noise_std}</span>
              </div>
            </div>
          </div>
        )}

        {!selectedId && (
          <div className="inspector-lab-overview">
            <div className="entity-header">
              <h3>{lab.name}</h3>
            </div>
            <div className="property-group">
              <div className="prop-row">
                <span className="prop-label">Revision</span>
                <span className="prop-value">rev {lab.revision}</span>
              </div>
              <div className="prop-row">
                <span className="prop-label">Equipment</span>
                <span className="prop-value">{lab.assets.length} items</span>
              </div>
              <div className="prop-row">
                <span className="prop-label">Pipes</span>
                <span className="prop-value">{lab.pipes.length} segments</span>
              </div>
              <div className="prop-row">
                <span className="prop-label">Sensors</span>
                <span className="prop-value">{lab.sensors.length} instruments</span>
              </div>
            </div>
            <div className="hint-box">
              <p>Click any equipment, pipe, or sensor in the 3D scene to inspect or configure its parameters.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
