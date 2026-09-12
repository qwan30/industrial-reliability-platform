/**
 * Top toolbar for lab status, mode switching, and camera controls.
 */

import {
  useEditorSlice,
  useCameraSlice,
  useConnectionSlice,
  labStore,
  type LabMode,
} from "./store";

export function LabToolbar() {
  const { lab, mode } = useEditorSlice();
  const { mode: cameraMode } = useCameraSlice();
  const { status: connectionStatus } = useConnectionSlice();

  const handleModeChange = (newMode: LabMode) => {
    labStore.setMode(newMode);
  };

  return (
    <header className="lab-toolbar">
      <div className="toolbar-left">
        <div className="brand-logo">
          <span className="logo-icon">⚙</span>
          <span className="logo-title">Virtual Lab</span>
        </div>

        {lab && (
          <div className="lab-badge">
            <span className="lab-name">{lab.name}</span>
            <span className="lab-rev">r{lab.revision}</span>
          </div>
        )}

        <span className="badge badge-source">SIMULATION</span>
      </div>

      <div className="toolbar-center">
        <div className="mode-segmented-control" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "BUILD"}
            className={`mode-btn ${mode === "BUILD" ? "active" : ""}`}
            onClick={() => handleModeChange("BUILD")}
          >
            Build
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "OPERATE"}
            className={`mode-btn ${mode === "OPERATE" ? "active" : ""}`}
            onClick={() => handleModeChange("OPERATE")}
          >
            Operate
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "INVESTIGATE"}
            className={`mode-btn ${mode === "INVESTIGATE" ? "active" : ""}`}
            onClick={() => handleModeChange("INVESTIGATE")}
          >
            Investigate
          </button>
        </div>
      </div>

      <div className="toolbar-right">
        {/* Camera toggles */}
        <div className="camera-controls">
          <button
            type="button"
            className={`btn btn-sm ${cameraMode === "ORBIT" ? "btn-secondary" : "btn-ghost"}`}
            onClick={() => labStore.setCameraMode("ORBIT")}
            title="Orbit Camera (drag to rotate, wheel to zoom)"
          >
            Orbit
          </button>
          <button
            type="button"
            className={`btn btn-sm ${cameraMode === "WALK" ? "btn-secondary" : "btn-ghost"}`}
            onClick={() => labStore.setCameraMode("WALK")}
            title="Walk Mode (WASD to walk)"
          >
            Walk
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => {
              // Dispatch home key press
              window.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyH" }));
            }}
            title="Reset Camera (H)"
          >
            Home
          </button>
        </div>

        {/* Connection status badge */}
        <div className="connection-indicator" title={`Stream: ${connectionStatus}`}>
          <span className={`status-dot ${connectionStatus.toLowerCase()}`} />
          <span className="status-label">{connectionStatus}</span>
        </div>
      </div>
    </header>
  );
}
