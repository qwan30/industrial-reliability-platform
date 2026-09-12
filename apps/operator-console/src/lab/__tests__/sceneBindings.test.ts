/**
 * Unit tests for 3D scene bindings, manifest parsing, and spatial calculations.
 */

import { describe, it, expect } from "vitest";
import {
  computePortWorldPosition,
  generateOrthogonalPath,
  GLB_FILES,
  LOCAL_ANCHORS,
} from "../sceneBindings";
import fs from "node:fs";
import path from "node:path";

describe("sceneBindings", () => {
  it("defines all 5 equipment GLB file paths", () => {
    expect(GLB_FILES.COMPRESSOR).toBe("/lab-assets/compressor.glb");
    expect(GLB_FILES.TANK).toBe("/lab-assets/tank.glb");
    expect(GLB_FILES.ISOLATION_VALVE).toBe("/lab-assets/isolation-valve.glb");
    expect(GLB_FILES.CONTROL_VALVE).toBe("/lab-assets/control-valve.glb");
    expect(GLB_FILES.DEMAND).toBe("/lab-assets/demand.glb");
  });

  it("defines local anchor offsets for all equipment types", () => {
    expect(LOCAL_ANCHORS.COMPRESSOR.OUT).toEqual([0.8, 0.5, 0.0]);
    expect(LOCAL_ANCHORS.TANK.A).toEqual([-0.45, 0.9, 0.0]);
    expect(LOCAL_ANCHORS.TANK.B).toEqual([0.45, 0.9, 0.0]);
    expect(LOCAL_ANCHORS.ISOLATION_VALVE.A).toEqual([-0.2, 0.3, 0.0]);
    expect(LOCAL_ANCHORS.ISOLATION_VALVE.B).toEqual([0.2, 0.3, 0.0]);
    expect(LOCAL_ANCHORS.DEMAND.IN).toEqual([-0.4, 0.6, 0.0]);
  });

  it("correctly calculates world position with rotation", () => {
    const assetPos: [number, number, number] = [2.0, 0.0, 3.0];

    // No rotation (0 rad)
    const pos0 = computePortWorldPosition("COMPRESSOR", assetPos, 0.0, "OUT");
    expect(pos0[0]).toBeCloseTo(2.8);
    expect(pos0[1]).toBeCloseTo(0.5);
    expect(pos0[2]).toBeCloseTo(3.0);

    // 90 deg rotation (PI / 2 rad)
    // local [0.8, 0.5, 0] rotated 90 deg around Y -> x'=0, z'=-0.8
    const pos90 = computePortWorldPosition("COMPRESSOR", assetPos, Math.PI / 2, "OUT");
    expect(pos90[0]).toBeCloseTo(2.0);
    expect(pos90[1]).toBeCloseTo(0.5);
    expect(pos90[2]).toBeCloseTo(2.2);
  });

  it("generates valid orthogonal pipe waypoints", () => {
    const p1: [number, number, number] = [-4.0, 0.9, 1.5];
    const p2: [number, number, number] = [0.0, 0.3, 1.5];

    const waypoints = generateOrthogonalPath(p1, p2, 0.35);
    expect(waypoints.length).toBeGreaterThanOrEqual(2);
    expect(waypoints[0]).toEqual(p1);
    expect(waypoints[waypoints.length - 1]).toEqual(p2);

    // Points transition through pipe elevation layer
    const intermediateY = waypoints.slice(1, -1).map((p) => p[1]);
    expect(intermediateY.every((y) => Math.abs(y - 0.35) < 0.01)).toBe(true);
  });

  it("verifies catalog.json manifest on disk contains all 7 generated assets", () => {
    const manifestPath = path.resolve(__dirname, "../../../public/lab-assets/catalog.json");
    expect(fs.existsSync(manifestPath)).toBe(true);

    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    expect(manifest.schema_version).toBe("lab-asset-manifest-v1");
    expect(manifest.origin).toBe("PROJECT_AUTHORED");
    expect(manifest.license).toBe("MIT");
    expect(manifest.units).toBe("meter");

    const assetKeys = Object.keys(manifest.assets);
    expect(assetKeys).toContain("compressor.glb");
    expect(assetKeys).toContain("tank.glb");
    expect(assetKeys).toContain("isolation-valve.glb");
    expect(assetKeys).toContain("control-valve.glb");
    expect(assetKeys).toContain("demand.glb");
    expect(assetKeys).toContain("pressure-sensor.glb");
    expect(assetKeys).toContain("flow-sensor.glb");

    for (const key of assetKeys) {
      const info = manifest.assets[key];
      expect(info.sha256).toBeDefined();
      expect(info.sha256.length).toBe(64);
      expect(info.size_bytes).toBeGreaterThan(1000);
      expect(info.anchors).toBeDefined();
    }
  });
});
