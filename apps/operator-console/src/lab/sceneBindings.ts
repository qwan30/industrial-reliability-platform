/**
 * 3D Scene bindings and spatial calculations for equipment, ports, and pipes.
 */

import type { AssetType, PortName } from "./types";

export const GLB_FILES: Record<AssetType, string> = {
  COMPRESSOR: "/lab-assets/compressor.glb",
  TANK: "/lab-assets/tank.glb",
  ISOLATION_VALVE: "/lab-assets/isolation-valve.glb",
  CONTROL_VALVE: "/lab-assets/control-valve.glb",
  DEMAND: "/lab-assets/demand.glb",
};

export const SENSOR_GLB_FILES = {
  PRESSURE: "/lab-assets/pressure-sensor.glb",
  FLOW: "/lab-assets/flow-sensor.glb",
};

// Local-space anchor coordinates (meters) matching the procedural assets
export const LOCAL_ANCHORS: Record<AssetType, Partial<Record<PortName, [number, number, number]>>> = {
  COMPRESSOR: {
    OUT: [0.8, 0.5, 0.0],
  },
  TANK: {
    A: [-0.45, 0.9, 0.0],
    B: [0.45, 0.9, 0.0],
  },
  ISOLATION_VALVE: {
    A: [-0.2, 0.3, 0.0],
    B: [0.2, 0.3, 0.0],
  },
  CONTROL_VALVE: {
    A: [-0.2, 0.3, 0.0],
    B: [0.2, 0.3, 0.0],
  },
  DEMAND: {
    IN: [-0.4, 0.6, 0.0],
  },
};

// Bounding box extents [half_width, half_height, half_depth]
export const ASSET_BOUNDS: Record<AssetType, [number, number, number]> = {
  COMPRESSOR: [0.8, 0.65, 0.5],
  TANK: [0.5, 1.1, 0.5],
  ISOLATION_VALVE: [0.25, 0.35, 0.15],
  CONTROL_VALVE: [0.25, 0.45, 0.25],
  DEMAND: [0.45, 0.65, 0.4],
};

/**
 * Compute the world-space coordinate of a port on an asset.
 */
export function computePortWorldPosition(
  assetType: AssetType,
  assetPos: [number, number, number],
  rotationYRad: number,
  port: PortName
): [number, number, number] {
  const local = LOCAL_ANCHORS[assetType]?.[port];
  if (!local) {
    return [...assetPos];
  }

  const [lx, ly, lz] = local;
  const cos = Math.cos(rotationYRad);
  const sin = Math.sin(rotationYRad);

  // Rotate around Y axis
  const rx = lx * cos + lz * sin;
  const ry = ly;
  const rz = -lx * sin + lz * cos;

  return [assetPos[0] + rx, assetPos[1] + ry, assetPos[2] + rz];
}

/**
 * Generate orthogonal route waypoints between two 3D port points.
 */
export function generateOrthogonalPath(
  p1: [number, number, number],
  p2: [number, number, number],
  pipeElevation: number = 0.35
): [number, number, number][] {
  const points: [number, number, number][] = [p1];

  // Route down/up to pipe elevation layer
  const corner1: [number, number, number] = [p1[0], pipeElevation, p1[2]];
  const corner2: [number, number, number] = [p2[0], pipeElevation, p1[2]];
  const corner3: [number, number, number] = [p2[0], pipeElevation, p2[2]];

  if (Math.abs(p1[1] - pipeElevation) > 0.05) {
    points.push(corner1);
  }
  if (Math.abs(p1[0] - p2[0]) > 0.05) {
    points.push(corner2);
  }
  if (Math.abs(p1[2] - p2[2]) > 0.05) {
    points.push(corner3);
  }
  points.push(p2);

  return points;
}
