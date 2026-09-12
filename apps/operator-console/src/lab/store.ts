/**
 * External reactive store for Virtual Lab state management using useSyncExternalStore.
 */

import { useSyncExternalStore } from "react";
import type {
  LabDefinition,
  Observation,
  PortName,
  RunSnapshot,
  RunSpeed,
  RunStatus,
} from "./types";

export type LabMode = "BUILD" | "OPERATE" | "INVESTIGATE";
export type SelectionKind = "ASSET" | "PIPE" | "SENSOR";
export type CameraMode = "ORBIT" | "WALK";
export type StreamConnectionStatus = "CONNECTED" | "CONNECTING" | "STALE" | "DISCONNECTED";

export interface LabState {
  editor: {
    mode: LabMode;
    lab: LabDefinition | null;
    isDirty: boolean;
  };
  run: {
    runId: string | null;
    status: RunStatus | "IDLE";
    tick: number;
    speed: RunSpeed;
    snapshot: RunSnapshot | null;
    telemetry: Record<string, number>; // sensor_id -> value
  };
  selection: {
    selectedId: string | null;
    selectedKind: SelectionKind | null;
    selectedPort: PortName | null;
  };
  camera: {
    mode: CameraMode;
    focusTarget: [number, number, number] | null;
    focusCounter: number;
  };
  connection: {
    status: StreamConnectionStatus;
  };
}

const initialState: LabState = {
  editor: {
    mode: "OPERATE",
    lab: null,
    isDirty: false,
  },
  run: {
    runId: null,
    status: "IDLE",
    tick: 0,
    speed: 1,
    snapshot: null,
    telemetry: {},
  },
  selection: {
    selectedId: null,
    selectedKind: null,
    selectedPort: null,
  },
  camera: {
    mode: "ORBIT",
    focusTarget: null,
    focusCounter: 0,
  },
  connection: {
    status: "DISCONNECTED",
  },
};

type Listener = () => void;

class LabStoreManager {
  private state: LabState = initialState;
  private listeners: Set<Listener> = new Set();

  getState = (): LabState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private setState(partial: Partial<LabState> | ((prev: LabState) => LabState)) {
    this.state = typeof partial === "function" ? partial(this.state) : { ...this.state, ...partial };
    this.listeners.forEach((l) => l());
  }

  // --- Actions ---

  setLab = (lab: LabDefinition | null) => {
    this.setState((prev) => ({
      ...prev,
      editor: { ...prev.editor, lab, isDirty: false },
    }));
  };

  updateLabDraft = (updater: (prev: LabDefinition) => LabDefinition) => {
    this.setState((prev) => {
      if (!prev.editor.lab) return prev;
      return {
        ...prev,
        editor: {
          ...prev.editor,
          lab: updater(prev.editor.lab),
          isDirty: true,
        },
      };
    });
  };

  setMode = (mode: LabMode) => {
    this.setState((prev) => ({
      ...prev,
      editor: { ...prev.editor, mode },
    }));
  };

  selectEntity = (id: string | null, kind: SelectionKind | null, port: PortName | null = null) => {
    this.setState((prev) => ({
      ...prev,
      selection: {
        selectedId: id,
        selectedKind: kind,
        selectedPort: port,
      },
    }));
  };

  clearSelection = () => {
    this.selectEntity(null, null, null);
  };

  setCameraMode = (mode: CameraMode) => {
    this.setState((prev) => ({
      ...prev,
      camera: { ...prev.camera, mode },
    }));
  };

  focusOn = (target: [number, number, number]) => {
    this.setState((prev) => ({
      ...prev,
      camera: {
        ...prev.camera,
        focusTarget: target,
        focusCounter: prev.camera.focusCounter + 1,
      },
    }));
  };

  setRunSnapshot = (snapshot: RunSnapshot) => {
    const telemetry: Record<string, number> = {};
    if (snapshot.observations) {
      for (const obs of snapshot.observations) {
        if (obs.value !== null) {
          telemetry[obs.sensor_id] = obs.value;
        }
      }
    }

    this.setState((prev) => ({
      ...prev,
      run: {
        ...prev.run,
        runId: snapshot.run_id,
        status: snapshot.status as RunStatus,
        tick: snapshot.tick,
        snapshot,
        telemetry: { ...prev.run.telemetry, ...telemetry },
      },
    }));
  };

  updateObservations = (obsList: Observation[]) => {
    const newTelemetry: Record<string, number> = {};
    for (const obs of obsList) {
      if (obs.value !== null) {
        newTelemetry[obs.sensor_id] = obs.value;
      }
    }
    this.setState((prev) => ({
      ...prev,
      run: {
        ...prev.run,
        telemetry: { ...prev.run.telemetry, ...newTelemetry },
      },
    }));
  };

  setConnectionStatus = (status: StreamConnectionStatus) => {
    this.setState((prev) => ({
      ...prev,
      connection: { status },
    }));
  };

  setRunSpeed = (speed: RunSpeed) => {
    this.setState((prev) => ({
      ...prev,
      run: { ...prev.run, speed },
    }));
  };
}

export const labStore = new LabStoreManager();

// React Hooks for selecting slices
export function useLabState<T>(selector: (state: LabState) => T): T {
  return useSyncExternalStore(
    labStore.subscribe,
    () => selector(labStore.getState()),
    () => selector(initialState)
  );
}

export function useEditorSlice() {
  return useLabState((s) => s.editor);
}

export function useRunSlice() {
  return useLabState((s) => s.run);
}

export function useSelectionSlice() {
  return useLabState((s) => s.selection);
}

export function useCameraSlice() {
  return useLabState((s) => s.camera);
}

export function useConnectionSlice() {
  return useLabState((s) => s.connection);
}
