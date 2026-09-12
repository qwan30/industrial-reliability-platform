import { LabIcon } from "./LabIcon";
import { useConnectionSlice, useEditorSlice, useRunSlice } from "./store";
export function LabStatusBar({ onReplay }: { onReplay?: () => void }) {
  const { status: connection } = useConnectionSlice();
  const { lab } = useEditorSlice();
  const { snapshot, status } = useRunSlice();
  return (
    <footer className="lab-statusbar">
      <div>
        <span className={`status-dot ${connection.toLowerCase()}`} />
        <span>
          {connection === "CONNECTED"
            ? "Connected to simulation engine"
            : connection === "STALE"
              ? "Simulation stream stale"
              : connection === "CONNECTING"
                ? "Connecting to simulation engine"
                : "Simulation engine offline"}
        </span>
      </div>
      <div>
        <LabIcon name="sensor" size={13} />
        <span>
          {snapshot?.observations.length ?? 0} observations ·{" "}
          {lab?.sensors.length ?? 0} sensors
        </span>
      </div>
      <div>
        <LabIcon name="cube" size={13} />
        <span>
          {status === "IDLE" ? "No active run" : `Run ${status.toLowerCase()}`}
        </span>
      </div>
      <span className="statusbar-api">API v2 · Simulation</span>
      {onReplay && (
        <button type="button" className="statusbar-replay" onClick={onReplay}>
          Historical Replay Console ↗
        </button>
      )}
    </footer>
  );
}
