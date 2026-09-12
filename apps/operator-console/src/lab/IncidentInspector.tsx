/**
 * Incident Inspector panel listing open and historical process/data alerts.
 */

import { useState } from "react";
import type { LabAlert } from "./types";
import { useRunSlice, useEditorSlice, labStore } from "./store";
import { EvidenceViewer } from "./EvidenceViewer";

export function IncidentInspector() {
  const { lab } = useEditorSlice();
  const { snapshot } = useRunSlice();
  const [selectedAlert, setSelectedAlert] = useState<LabAlert | null>(null);

  const alerts = snapshot?.alerts || [];

  const handleSelectAlert = (alert: LabAlert) => {
    setSelectedAlert(alert);
    // Highlight affected asset or sensor
    labStore.selectEntity(alert.asset_id, "ASSET");
    const asset = lab?.assets.find((a) => a.asset_id === alert.asset_id);
    if (asset) {
      labStore.focusOn(asset.position_m);
    }
  };

  return (
    <div className="lab-panel lab-incidents-panel">
      <div className="panel-header">
        <span className="panel-title">Incidents & Alarms ({alerts.length})</span>
      </div>

      <div className="incidents-content">
        {alerts.length === 0 ? (
          <div className="no-incidents-msg">
            <span className="clean-icon">✓</span>
            <p>No open process limits or data quality alarms</p>
          </div>
        ) : (
          <div className="alerts-list">
            {alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className={`alert-card origin-${alert.origin.toLowerCase()} ${
                  selectedAlert?.alert_id === alert.alert_id ? "selected" : ""
                }`}
                onClick={() => handleSelectAlert(alert)}
              >
                <div className="alert-card-header">
                  <span className={`badge badge-alert-${alert.origin.toLowerCase()}`}>
                    {alert.origin.replace("_", " ")}
                  </span>
                  <span className="alert-kind">{alert.kind}</span>
                </div>

                <div className="alert-card-details">
                  <div className="alert-meta-row">
                    <span className="meta-label">Sensor:</span>
                    <span className="meta-val">{alert.sensor_id.slice(0, 8)}</span>
                  </div>
                  <div className="alert-meta-row">
                    <span className="meta-label">Ticks:</span>
                    <span className="meta-val">
                      {alert.first_tick} → {alert.last_tick} ({(alert.last_tick * 0.05).toFixed(1)}s)
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  className="btn btn-sm btn-ghost view-evidence-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedAlert(alert);
                  }}
                >
                  Inspect Evidence →
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {selectedAlert && (
        <EvidenceViewer alert={selectedAlert} onClose={() => setSelectedAlert(null)} />
      )}
    </div>
  );
}
