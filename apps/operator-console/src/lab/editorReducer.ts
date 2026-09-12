/**
 * Pure reducer and undo/redo manager for free-form Virtual Lab authoring.
 */

import type { Asset, AssetType, LabDefinition, Pipe, PortRef, Sensor } from "./types";

export const DEFAULT_PARAMETERS_BY_ASSET_TYPE: Record<AssetType, Record<string, number | boolean>> = {
  TANK: { volume_m3: 0.5, initial_pressure_pa: 400000.0 },
  COMPRESSOR: { q_nom_kg_s: 0.02, p_max_pa: 900000.0, load: 1.0, enabled: true, initial_pressure_pa: 400000.0 },
  ISOLATION_VALVE: { conductance_kg_s_pa: 2e-7, opening: 1.0, initial_pressure_pa: 400000.0 },
  CONTROL_VALVE: { conductance_kg_s_pa: 2e-7, opening: 1.0, initial_pressure_pa: 400000.0 },
  DEMAND: { conductance_kg_s_pa: 1e-8, load_factor: 1.0, initial_pressure_pa: 400000.0 },
};

export type EditorAction =
  | { type: "SET_LAB"; payload: LabDefinition }
  | { type: "ADD_ASSET"; payload: { assetType: AssetType; position_m: [number, number, number] } }
  | { type: "MOVE_ASSET"; payload: { assetId: string; position_m: [number, number, number] } }
  | { type: "ROTATE_ASSET"; payload: { assetId: string; deltaRad: number } }
  | { type: "UPDATE_ASSET_PARAMS"; payload: { assetId: string; parameters: Record<string, number | boolean> } }
  | { type: "DELETE_ASSET"; payload: { assetId: string } }
  | { type: "ADD_PIPE"; payload: { from_port: PortRef; to_port: PortRef; conductance_kg_s_pa?: number } }
  | { type: "DELETE_PIPE"; payload: { pipeId: string } }
  | { type: "ADD_SENSOR"; payload: Omit<Sensor, "sensor_id"> }
  | { type: "DELETE_SENSOR"; payload: { sensorId: string } }
  | { type: "UNDO" }
  | { type: "REDO" };

export interface EditorHistoryState {
  present: LabDefinition | null;
  past: LabDefinition[];
  future: LabDefinition[];
}

const MAX_HISTORY = 100;

export function initialEditorState(lab: LabDefinition | null = null): EditorHistoryState {
  return {
    present: lab,
    past: [],
    future: [],
  };
}

function snapToGrid(val: number, step: number = 0.25): number {
  return Math.round(val / step) * step;
}

export function editorReducer(
  state: EditorHistoryState,
  action: EditorAction
): EditorHistoryState {
  if (action.type === "SET_LAB") {
    return {
      present: action.payload,
      past: [],
      future: [],
    };
  }

  if (action.type === "UNDO") {
    if (state.past.length === 0 || !state.present) return state;
    const previous = state.past[state.past.length - 1];
    const newPast = state.past.slice(0, state.past.length - 1);
    return {
      present: previous,
      past: newPast,
      future: [state.present, ...state.future].slice(0, MAX_HISTORY),
    };
  }

  if (action.type === "REDO") {
    if (state.future.length === 0 || !state.present) return state;
    const next = state.future[0];
    const newFuture = state.future.slice(1);
    return {
      present: next,
      past: [...state.past, state.present].slice(-MAX_HISTORY),
      future: newFuture,
    };
  }

  if (!state.present) return state;
  const current = state.present;
  let nextLab: LabDefinition | null = null;

  switch (action.type) {
    case "ADD_ASSET": {
      const snappedPos: [number, number, number] = [
        snapToGrid(action.payload.position_m[0]),
        0,
        snapToGrid(action.payload.position_m[2]),
      ];

      const newAsset: Asset = {
        asset_id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `asset-${Date.now()}`,
        type: action.payload.assetType,
        position_m: snappedPos,
        rotation_y_rad: 0,
        parameters: { ...DEFAULT_PARAMETERS_BY_ASSET_TYPE[action.payload.assetType] },
      };

      nextLab = {
        ...current,
        assets: [...current.assets, newAsset],
      };
      break;
    }

    case "MOVE_ASSET": {
      const snappedPos: [number, number, number] = [
        snapToGrid(action.payload.position_m[0]),
        0,
        snapToGrid(action.payload.position_m[2]),
      ];
      nextLab = {
        ...current,
        assets: current.assets.map((a) =>
          a.asset_id === action.payload.assetId ? { ...a, position_m: snappedPos } : a
        ),
      };
      break;
    }

    case "ROTATE_ASSET": {
      nextLab = {
        ...current,
        assets: current.assets.map((a) => {
          if (a.asset_id !== action.payload.assetId) return a;
          const newRot = (a.rotation_y_rad + action.payload.deltaRad) % (Math.PI * 2);
          return { ...a, rotation_y_rad: newRot };
        }),
      };
      break;
    }

    case "UPDATE_ASSET_PARAMS": {
      nextLab = {
        ...current,
        assets: current.assets.map((a) =>
          a.asset_id === action.payload.assetId
            ? { ...a, parameters: { ...a.parameters, ...action.payload.parameters } }
            : a
        ),
      };
      break;
    }

    case "DELETE_ASSET": {
      const targetId = action.payload.assetId;
      // Cascade delete: remove connected pipes and sensors
      const remainingAssets = current.assets.filter((a) => a.asset_id !== targetId);
      const remainingPipes = current.pipes.filter(
        (p) => p.from_port.asset_id !== targetId && p.to_port.asset_id !== targetId
      );
      const remainingSensors = current.sensors.filter((s) => {
        if (s.kind === "PRESSURE") {
          return (s.target as PortRef).asset_id !== targetId;
        }
        return true;
      });

      nextLab = {
        ...current,
        assets: remainingAssets,
        pipes: remainingPipes,
        sensors: remainingSensors,
      };
      break;
    }

    case "ADD_PIPE": {
      const newPipe: Pipe = {
        pipe_id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `pipe-${Date.now()}`,
        from_port: action.payload.from_port,
        to_port: action.payload.to_port,
        conductance_kg_s_pa: action.payload.conductance_kg_s_pa ?? 2e-7,
        waypoints_m: [],
      };

      nextLab = {
        ...current,
        pipes: [...current.pipes, newPipe],
      };
      break;
    }

    case "DELETE_PIPE": {
      const targetPipeId = action.payload.pipeId;
      const remainingPipes = current.pipes.filter((p) => p.pipe_id !== targetPipeId);
      const remainingSensors = current.sensors.filter(
        (s) => !(s.kind === "FLOW" && (s.target as string) === targetPipeId)
      );

      nextLab = {
        ...current,
        pipes: remainingPipes,
        sensors: remainingSensors,
      };
      break;
    }

    case "ADD_SENSOR": {
      const newSensor: Sensor = {
        sensor_id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `sensor-${Date.now()}`,
        ...action.payload,
      };

      nextLab = {
        ...current,
        sensors: [...current.sensors, newSensor],
      };
      break;
    }

    case "DELETE_SENSOR": {
      nextLab = {
        ...current,
        sensors: current.sensors.filter((s) => s.sensor_id !== action.payload.sensorId),
      };
      break;
    }

    default:
      return state;
  }

  if (!nextLab) return state;

  return {
    present: nextLab,
    past: [...state.past, current].slice(-MAX_HISTORY),
    future: [],
  };
}
