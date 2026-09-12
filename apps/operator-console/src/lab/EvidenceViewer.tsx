/**
 * Evidence Viewer modal inspecting immutable alert evidence and telemetry bundle.
 */

import type { LabAlert } from "./types";
import { useRunSlice } from "./store";

interface EvidenceViewerProps {
  alert: LabAlert;
  onClose: () => void;
}

export function EvidenceViewer({ alert, onClose }: EvidenceViewerProps) {
  const { snapshot } = useRunSlice();

  const windowObservations = (snapshot?.observations || []).filter(
    (o) => o.sensor_id === alert.sensor_id && o.tick >= alert.first_tick && o.tick <= alert.last_tick
  );

  return (
    <div className="evidence-modal-backdrop" onClick={onClose}>
      <div className="evidence-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-box">
            <h3>Evidence Bundle Inspection</h3>
            <span className="evidence-id">ID: {alert.alert_id}</span>
          </div>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="modal-body">
          <div className="evidence-summary-grid">
            <div className="summary-item">
              <span className="summary-label">Origin</span>
              <span className="summary-value">{alert.origin}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Condition</span>
              <span className="summary-value">{alert.kind}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Tick Interval</span>
              <span className="summary-value">
                [{alert.first_tick}, {alert.last_tick}] ({(alert.first_tick * 0.05).toFixed(1)}s → {(alert.last_tick * 0.05).toFixed(1)}s)
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Status</span>
              <span className="summary-value">{alert.state}</span>
            </div>
          </div>

          <div className="evidence-table-section">
            <div className="section-title">Sampled Sensor Window Observations</div>
            {windowObservations.length === 0 ? (
              <p className="text-muted">No window observations currently in stream buffer.</p>
            ) : (
              <table className="evidence-table">
                <thead>
                  <tr>
                    <th>Tick</th>
                    <th>Time</th>
                    <th>Measured Value</th>
                    <th>Unit</th>
                    <th>Quality</th>
                  </tr>
                </thead>
                <tbody>
                  {windowObservations.map((obs) => (
                    <tr key={`${obs.sensor_id}_${obs.tick}`}>
                      <td>{obs.tick}</td>
                      <td>{(obs.tick * 0.05).toFixed(1)}s</td>
                      <td>{obs.value !== null ? obs.value.toFixed(4) : "—"}</td>
                      <td>{obs.unit}</td>
                      <td>
                        <span className={`quality-badge quality-${obs.quality.toLowerCase()}`}>
                          {obs.quality}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="modal-footer">
          <span className="provenance-note">Evidence source: SIMULATION runtime verified</span>
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
