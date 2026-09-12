/**
 * Unit tests for useLabStream hook and SSE message handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useLabStream } from "../useLabStream";
import { labStore } from "../store";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(event: string, callback: (e: MessageEvent) => void) {
    this.listeners[event] = this.listeners[event] || [];
    this.listeners[event].push(callback);
  }

  removeEventListener(event: string, callback: (e: MessageEvent) => void) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((cb) => cb !== callback);
    }
  }

  simulateEvent(event: string, data: unknown) {
    const handlers = this.listeners[event] || [];
    const msg = { data: JSON.stringify(data) } as MessageEvent;
    handlers.forEach((h) => h(msg));
  }

  close() {}
}

describe("useLabStream", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    (global as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it("subscribes to stream URL and updates status to CONNECTED on open", () => {
    const { unmount } = renderHook(() => useLabStream("run-123"));

    expect(MockEventSource.instances.length).toBe(1);
    const instance = MockEventSource.instances[0];
    expect(instance.url).toContain("/v2/runs/run-123/stream");

    // Simulate open
    instance.onopen?.();
    expect(labStore.getState().connection.status).toBe("CONNECTED");

    unmount();
    expect(labStore.getState().connection.status).toBe("DISCONNECTED");
  });

  it("processes snapshot event into store state", () => {
    renderHook(() => useLabStream("run-456"));
    const instance = MockEventSource.instances[0];

    const mockSnapshot = {
      run_id: "run-456",
      tick: 20,
      status: "RUNNING",
      control_revision: 2,
      event_sequence: 5,
      physical: {
        tick: 20,
        pressures_pa: { "comp-1": 450000 },
        flows_kg_s: {},
        operating_modes: {},
      },
      observations: [
        {
          run_id: "run-456",
          asset_id: "comp-1",
          sensor_id: "sensor-1",
          tick: 20,
          unit: "Pa",
          value: 450120.0,
          quality: "GOOD",
          profile_digest: "digest",
          source_mode: "SIMULATION",
        },
      ],
      pending_commands: [],
      alerts: [],
      connection_status: "CONNECTED",
    };

    instance.simulateEvent("snapshot", mockSnapshot);

    const runState = labStore.getState().run;
    expect(runState.runId).toBe("run-456");
    expect(runState.tick).toBe(20);
    expect(runState.status).toBe("RUNNING");
    expect(runState.telemetry["sensor-1"]).toBe(450120.0);
  });
});
