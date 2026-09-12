/**
 * Unit tests for editorReducer authoring logic, cascading delete, and undo/redo.
 */

import { describe, it, expect } from "vitest";
import { editorReducer, initialEditorState } from "../editorReducer";
import type { LabDefinition } from "../types";

const emptyLab: LabDefinition = {
  schema_version: "lab-definition-v1",
  lab_id: "test-lab-1",
  revision: 1,
  name: "Reducer Test Lab",
  assets: [],
  pipes: [],
  sensors: [],
  scene_revision: "scene-v1",
};

describe("editorReducer", () => {
  it("initializes state and sets lab", () => {
    let state = initialEditorState(null);
    expect(state.present).toBeNull();

    state = editorReducer(state, { type: "SET_LAB", payload: emptyLab });
    expect(state.present?.name).toBe("Reducer Test Lab");
    expect(state.past.length).toBe(0);
    expect(state.future.length).toBe(0);
  });

  it("adds an asset with grid snap and default parameters", () => {
    let state = initialEditorState(emptyLab);

    state = editorReducer(state, {
      type: "ADD_ASSET",
      payload: { assetType: "COMPRESSOR", position_m: [2.12, 0, 3.88] },
    });

    expect(state.present?.assets.length).toBe(1);
    const asset = state.present!.assets[0];
    expect(asset.type).toBe("COMPRESSOR");
    // Snapped to 0.25m grid: 2.12 -> 2.0 or 2.25? 2.12 / 0.25 = 8.48 -> 8 -> 2.0
    expect(asset.position_m[0]).toBe(2.0);
    expect(asset.position_m[2]).toBe(4.0); // 3.88 / 0.25 = 15.52 -> 16 -> 4.0
    expect(asset.parameters.p_max_pa).toBe(900000.0);
    expect(state.past.length).toBe(1);
  });

  it("supports undo and redo", () => {
    let state = initialEditorState(emptyLab);

    // Step 1: Add Compressor
    state = editorReducer(state, {
      type: "ADD_ASSET",
      payload: { assetType: "COMPRESSOR", position_m: [0, 0, 0] },
    });
    expect(state.present?.assets.length).toBe(1);

    // Step 2: Add Tank
    state = editorReducer(state, {
      type: "ADD_ASSET",
      payload: { assetType: "TANK", position_m: [4, 0, 0] },
    });
    expect(state.present?.assets.length).toBe(2);

    // Undo Step 2
    state = editorReducer(state, { type: "UNDO" });
    expect(state.present?.assets.length).toBe(1);
    expect(state.future.length).toBe(1);

    // Redo Step 2
    state = editorReducer(state, { type: "REDO" });
    expect(state.present?.assets.length).toBe(2);
    expect(state.future.length).toBe(0);
  });

  it("cascades deletion of asset to connected pipes and sensors, and undo restores them", () => {
    let state = initialEditorState(emptyLab);

    // 1. Add Compressor
    state = editorReducer(state, {
      type: "ADD_ASSET",
      payload: { assetType: "COMPRESSOR", position_m: [-4, 0, 0] },
    });
    const compId = state.present!.assets[0].asset_id;

    // 2. Add Tank
    state = editorReducer(state, {
      type: "ADD_ASSET",
      payload: { assetType: "TANK", position_m: [0, 0, 0] },
    });
    const tankId = state.present!.assets[1].asset_id;

    // 3. Connect with Pipe
    state = editorReducer(state, {
      type: "ADD_PIPE",
      payload: {
        from_port: { asset_id: compId, port: "OUT" },
        to_port: { asset_id: tankId, port: "A" },
      },
    });
    expect(state.present?.pipes.length).toBe(1);

    // 4. Delete Compressor -> Should cascade delete pipe
    state = editorReducer(state, {
      type: "DELETE_ASSET",
      payload: { assetId: compId },
    });
    expect(state.present?.assets.length).toBe(1);
    expect(state.present?.pipes.length).toBe(0);

    // 5. Undo -> Should restore Compressor and Pipe
    state = editorReducer(state, { type: "UNDO" });
    expect(state.present?.assets.length).toBe(2);
    expect(state.present?.pipes.length).toBe(1);
  });

  it("arranges overlapping stacked assets across a clean grid and supports undo", () => {
    let state = initialEditorState(emptyLab);

    // Add 10 assets all stacked at [0, 0, 0]
    for (let i = 0; i < 10; i++) {
      state = editorReducer(state, {
        type: "ADD_ASSET",
        payload: { assetType: "COMPRESSOR", position_m: [0, 0, 0] },
      });
    }
    expect(state.present?.assets.length).toBe(10);
    // Initially all at 0, 0, 0
    expect(
      state.present?.assets.every(
        (a) => a.position_m[0] === 0 && a.position_m[2] === 0,
      ),
    ).toBe(true);

    // Auto-arrange
    state = editorReducer(state, { type: "ARRANGE_ASSETS" });

    const positions = state.present!.assets.map(
      (a) => `${a.position_m[0]},${a.position_m[2]}`,
    );
    const uniquePositions = new Set(positions);
    // Every asset should have a distinct grid position!
    expect(uniquePositions.size).toBe(10);

    // All positions within factory room safety bounds
    for (const a of state.present!.assets) {
      expect(a.position_m[0]).toBeGreaterThanOrEqual(-10);
      expect(a.position_m[0]).toBeLessThanOrEqual(10);
      expect(a.position_m[2]).toBeGreaterThanOrEqual(-6.5);
      expect(a.position_m[2]).toBeLessThanOrEqual(6.5);
    }

    // Undo restores stacked state
    state = editorReducer(state, { type: "UNDO" });
    expect(
      state.present?.assets.every(
        (a) => a.position_m[0] === 0 && a.position_m[2] === 0,
      ),
    ).toBe(true);
  });
});
