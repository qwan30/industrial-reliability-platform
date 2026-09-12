/**
 * 3D Scene viewport container using React Three Fiber Canvas.
 */

import { useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import { Room } from "./Room";
import { CameraRig } from "./CameraRig";
import { Equipment } from "./Equipment";
import { PipeMesh } from "./PipeMesh";
import { SensorMesh } from "./SensorMesh";
import { PortConnector } from "./PortConnector";
import { useEditorSlice, labStore } from "./store";

export function LabScene() {
  const { lab } = useEditorSlice();
  const [contextLost, setContextLost] = useState(false);

  // Asset and pipe lookup maps for fast wiring reference
  const assetMap = useMemo(() => {
    const map = new Map();
    if (lab) {
      for (const a of lab.assets) {
        map.set(a.asset_id, a);
      }
    }
    return map;
  }, [lab]);

  const pipeMap = useMemo(() => {
    const map = new Map();
    if (lab) {
      for (const p of lab.pipes) {
        map.set(p.pipe_id, p);
      }
    }
    return map;
  }, [lab]);

  if (contextLost) {
    return (
      <div className="webgl-error-overlay">
        <div className="error-card">
          <h3>3D Graphics Context Interrupted</h3>
          <p>The GPU device context was lost or reset.</p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setContextLost(false)}
          >
            Recover 3D Viewport
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="lab-scene-container" style={{ width: "100%", height: "100%", position: "relative" }}>
      <Canvas
        shadows
        gl={{
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.0,
          antialias: true,
          powerPreference: "high-performance",
        }}
        dpr={[1, 1.5]}
        camera={{ position: [12, 10, 14], fov: 45, near: 0.1, far: 100 }}
        onPointerMissed={() => labStore.clearSelection()}
        onCreated={({ gl }) => {
          const dom = gl.domElement;
          dom.addEventListener("webglcontextlost", (e) => {
            e.preventDefault();
            setContextLost(true);
          });
          dom.addEventListener("webglcontextrestored", () => {
            setContextLost(false);
          });
        }}
      >
        <Room />
        <CameraRig />

        {/* Equipment */}
        {lab?.assets.map((asset) => (
          <Equipment key={asset.asset_id} asset={asset} />
        ))}

        {/* Pipes */}
        {lab?.pipes.map((pipe) => (
          <PipeMesh key={pipe.pipe_id} pipe={pipe} assetMap={assetMap} />
        ))}

        {/* Sensors */}
        {lab?.sensors.map((sensor) => (
          <SensorMesh
            key={sensor.sensor_id}
            sensor={sensor}
            assetMap={assetMap}
            pipeMap={pipeMap}
          />
        ))}
        <PortConnector
          assetMap={assetMap}
          onConnectPorts={(from, to) => {
            labStore.updateLabDraft((prev) => ({
              ...prev,
              pipes: [
                ...prev.pipes,
                {
                  pipe_id:
                    typeof crypto !== "undefined" && crypto.randomUUID
                      ? crypto.randomUUID()
                      : `pipe-${Date.now()}`,
                  from_port: from,
                  to_port: to,
                  conductance_kg_s_pa: 2e-7,
                  waypoints_m: [],
                },
              ],
            }));
          }}
        />
      </Canvas>
    </div>
  );
}
