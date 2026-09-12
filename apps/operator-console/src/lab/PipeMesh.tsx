/**
 * 3D Pipe rendering with orthogonal routing, tube geometry, and selection highlight.
 */

import { useMemo } from "react";
import * as THREE from "three";
import type { Asset, Pipe } from "./types";
import { computePortWorldPosition, generateOrthogonalPath } from "./sceneBindings";
import { useSelectionSlice, labStore } from "./store";

interface PipeMeshProps {
  pipe: Pipe;
  assetMap: Map<string, Asset>;
}

export function PipeMesh({ pipe, assetMap }: PipeMeshProps) {
  const { selectedId } = useSelectionSlice();
  const isSelected = selectedId === pipe.pipe_id;

  const fromAsset = assetMap.get(pipe.from_port.asset_id);
  const toAsset = assetMap.get(pipe.to_port.asset_id);

  const geometry = useMemo(() => {
    if (!fromAsset || !toAsset) return null;

    const startPos = computePortWorldPosition(
      fromAsset.type,
      fromAsset.position_m,
      fromAsset.rotation_y_rad,
      pipe.from_port.port
    );
    const endPos = computePortWorldPosition(
      toAsset.type,
      toAsset.position_m,
      toAsset.rotation_y_rad,
      pipe.to_port.port
    );

    const waypoints =
      pipe.waypoints_m && pipe.waypoints_m.length > 0
        ? [startPos, ...pipe.waypoints_m, endPos]
        : generateOrthogonalPath(startPos, endPos, 0.35);

    const vPoints = waypoints.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
    const curve = new THREE.CatmullRomCurve3(vPoints, false, "chordal", 0.05);

    return new THREE.TubeGeometry(curve, 48, 0.035, 12, false);
  }, [fromAsset, toAsset, pipe]);

  if (!geometry) return null;

  return (
    <mesh
      geometry={geometry}
      onClick={(e) => {
        e.stopPropagation();
        labStore.selectEntity(pipe.pipe_id, "PIPE");
      }}
    >
      <meshStandardMaterial
        color={isSelected ? 0x00a8ff : 0x89949f}
        roughness={0.25}
        metalness={0.8}
        emissive={isSelected ? 0x0055aa : 0x000000}
        emissiveIntensity={isSelected ? 0.4 : 0}
      />
    </mesh>
  );
}
