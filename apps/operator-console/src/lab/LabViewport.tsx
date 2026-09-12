import { useState } from "react";
import { LabScene } from "./LabScene";
import { LabIcon } from "./LabIcon";
import { EQUIPMENT_LABELS } from "./EquipmentCatalog";
import {
  labStore,
  useCameraSlice,
  useEditorSlice,
  useSelectionSlice,
} from "./store";

function TopologyView() {
  const { lab } = useEditorSlice();
  const { selectedId } = useSelectionSlice();
  if (!lab?.assets.length)
    return (
      <div className="viewport-empty">
        <LabIcon name="topology" size={32} />
        <h2>No topology yet</h2>
        <p>Add equipment in Build to create your pneumatic system.</p>
      </div>
    );
  const xs = lab.assets.map((asset) => asset.position_m[0]);
  const zs = lab.assets.map((asset) => asset.position_m[2]);
  const minX = Math.min(...xs),
    minZ = Math.min(...zs);
  const spanX = Math.max(...xs) - minX || 1,
    spanZ = Math.max(...zs) - minZ || 1;
  const points = new Map(
    lab.assets.map((asset) => [
      asset.asset_id,
      {
        x: 70 + ((asset.position_m[0] - minX) / spanX) * 460,
        y: 70 + ((asset.position_m[2] - minZ) / spanZ) * 340,
      },
    ]),
  );
  return (
    <div className="topology-view">
      <svg
        viewBox="0 0 600 480"
        role="img"
        aria-label="Lab connectivity diagram"
      >
        {lab.pipes.map((pipe) => {
          const from = points.get(pipe.from_port.asset_id),
            to = points.get(pipe.to_port.asset_id);
          return from && to ? (
            <path
              key={pipe.pipe_id}
              d={`M${from.x} ${from.y} H${(from.x + to.x) / 2} V${to.y} H${to.x}`}
              fill="none"
              stroke="#47728c"
              strokeWidth="2"
            >
              <title>
                {pipe.pipe_id}: {pipe.from_port.asset_id} →{" "}
                {pipe.to_port.asset_id}
              </title>
            </path>
          ) : null;
        })}
        {lab.assets.map((asset) => {
          const point = points.get(asset.asset_id)!;
          return (
            <g key={asset.asset_id}>
              <circle
                cx={point.x}
                cy={point.y}
                r="13"
                fill={asset.asset_id === selectedId ? "#00a8ff" : "#142b3b"}
                stroke="#66c5f5"
                strokeWidth="2"
              />
              <text
                x={point.x}
                y={point.y + 32}
                textAnchor="middle"
                fill="#d5e4ef"
                fontSize="11"
              >
                {asset.asset_id}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="topology-assets" aria-label="Select topology equipment">
        {lab.assets.map((asset) => (
          <button
            key={asset.asset_id}
            type="button"
            className={`btn btn-sm ${selectedId === asset.asset_id ? "btn-secondary" : "btn-ghost"}`}
            aria-label={`Select ${asset.asset_id}`}
            aria-pressed={selectedId === asset.asset_id}
            onClick={() => labStore.selectEntity(asset.asset_id, "ASSET")}
          >
            <LabIcon name={EQUIPMENT_LABELS[asset.type].icon} size={14} />
            {asset.asset_id}
          </button>
        ))}
      </div>
    </div>
  );
}

export function LabViewport() {
  const [view, setView] = useState<"3d" | "topology">("3d");
  const { mode: cameraMode } = useCameraSlice();
  const { lab } = useEditorSlice();
  return (
    <div className="lab-viewport">
      <div className="viewport-heading">
        <div
          className="workspace-tabs"
          role="group"
          aria-label="Digital twin view"
        >
          <button
            type="button"
            className={view === "3d" ? "active" : ""}
            aria-pressed={view === "3d"}
            onClick={() => setView("3d")}
          >
            <LabIcon name="cube" size={15} />
            3D Twin
          </button>
          <button
            type="button"
            className={view === "topology" ? "active" : ""}
            aria-pressed={view === "topology"}
            onClick={() => setView("topology")}
          >
            <LabIcon name="topology" size={15} />
            Topology
          </button>
        </div>
        <span className="viewport-source">SIMULATION</span>
      </div>
      <div className="viewport-canvas">
        {view === "3d" ? (
          <>
            <LabScene />
            <div
              className="viewport-camera"
              role="group"
              aria-label="Camera controls"
            >
              <button
                type="button"
                aria-label="Orbit camera"
                title="Orbit camera · drag to rotate"
                aria-pressed={cameraMode === "ORBIT"}
                onClick={() => labStore.setCameraMode("ORBIT")}
              >
                <LabIcon name="orbit" />
              </button>
              <button
                type="button"
                aria-label="Walk camera"
                title="Walk camera · WASD"
                aria-pressed={cameraMode === "WALK"}
                onClick={() => labStore.setCameraMode("WALK")}
              >
                <LabIcon name="walk" />
              </button>
              <button
                type="button"
                aria-label="Reset camera"
                title="Reset camera · H"
                onClick={() =>
                  window.dispatchEvent(
                    new KeyboardEvent("keydown", { code: "KeyH" }),
                  )
                }
              >
                <LabIcon name="home" />
              </button>
            </div>
            <div className="viewport-caption">
              <span>
                {lab?.assets.length ?? 0} assets <i>·</i>{" "}
                {lab?.pipes.length ?? 0} connections
              </span>
              <span>
                {cameraMode === "ORBIT"
                  ? "Drag to orbit · Scroll to zoom"
                  : "WASD to walk · Drag to look"}
              </span>
            </div>
          </>
        ) : (
          <TopologyView />
        )}
      </div>
    </div>
  );
}
