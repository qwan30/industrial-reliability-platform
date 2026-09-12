/**
 * 3D Sensor rendering attached to asset ports or pipe midpoints.
 */

import { useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import type { Asset, Pipe, PortRef, Sensor } from "./types";
import { SENSOR_GLB_FILES, computePortWorldPosition } from "./sceneBindings";
import { useSelectionSlice, labStore } from "./store";

Object.values(SENSOR_GLB_FILES).forEach((url) => useGLTF.preload(url));

interface SensorMeshProps {
  sensor: Sensor;
  assetMap: Map<string, Asset>;
  pipeMap: Map<string, Pipe>;
}

export function SensorMesh({ sensor, assetMap, pipeMap }: SensorMeshProps) {
  const { selectedId } = useSelectionSlice();
  const isSelected = selectedId === sensor.sensor_id;

  const glbUrl = sensor.kind === "PRESSURE" ? SENSOR_GLB_FILES.PRESSURE : SENSOR_GLB_FILES.FLOW;
  const { scene } = useGLTF(glbUrl);
  const clonedScene = useMemo(() => scene.clone(true), [scene]);

  // Compute world position
  const position = useMemo((): [number, number, number] | null => {
    if (sensor.kind === "PRESSURE") {
      const target = sensor.target as PortRef;
      const asset = assetMap.get(target.asset_id);
      if (!asset) return null;
      const portPos = computePortWorldPosition(asset.type, asset.position_m, asset.rotation_y_rad, target.port);
      // Place sensor on top of the port
      return [portPos[0], portPos[1] + 0.08, portPos[2]];
    } else {
      // Flow sensor on pipe
      const pipeId = sensor.target as string;
      const pipe = pipeMap.get(pipeId);
      if (!pipe) return null;
      const fromAsset = assetMap.get(pipe.from_port.asset_id);
      const toAsset = assetMap.get(pipe.to_port.asset_id);
      if (!fromAsset || !toAsset) return null;

      const p1 = computePortWorldPosition(fromAsset.type, fromAsset.position_m, fromAsset.rotation_y_rad, pipe.from_port.port);
      const p2 = computePortWorldPosition(toAsset.type, toAsset.position_m, toAsset.rotation_y_rad, pipe.to_port.port);
      return [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, (p1[2] + p2[2]) / 2];
    }
  }, [sensor, assetMap, pipeMap]);

  if (!position) return null;

  return (
    <group
      position={position}
      onClick={(e) => {
        e.stopPropagation();
        labStore.selectEntity(sensor.sensor_id, "SENSOR");
        labStore.focusOn(position);
      }}
    >
      <primitive object={clonedScene} />

      {isSelected && (
        <mesh position={[0, 0.1, 0]}>
          <sphereGeometry args={[0.15, 16, 16]} />
          <meshBasicMaterial color={0x00ff88} wireframe transparent opacity={0.6} />
        </mesh>
      )}
    </group>
  );
}
