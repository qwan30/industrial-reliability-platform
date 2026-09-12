import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SystemOverview } from "../SystemOverview";
import { labStore } from "../store";
import type { RunSnapshot } from "../types";

const snapshot: RunSnapshot = {
  run_id: "overview-run",
  tick: 20,
  status: "RUNNING",
  control_revision: 0,
  event_sequence: 0,
  physical: {
    tick: 20,
    pressures_pa: { c1: 800000 },
    flows_kg_s: { p1: 0.3 },
    operating_modes: {},
  },
  observations: [
    {
      run_id: "overview-run",
      tick: 20,
      asset_id: "c1",
      sensor_id: "s1",
      unit: "Pa",
      value: 800000,
      quality: "GOOD",
      source_mode: "SIMULATION",
      profile_digest: "1",
    },
    {
      run_id: "overview-run",
      tick: 20,
      asset_id: "c1",
      sensor_id: "s2",
      unit: "Pa",
      value: null,
      quality: "MISSING",
      source_mode: "SIMULATION",
      profile_digest: "1",
    },
  ],
  pending_commands: [],
  alerts: [
    {
      alert_id: "a1",
      run_id: "overview-run",
      asset_id: "c1",
      sensor_id: "s1",
      kind: "ABOVE_LIMIT",
      origin: "PROCESS_LIMIT",
      state: "OPEN",
      first_tick: 10,
      last_tick: 20,
    },
    {
      alert_id: "a2",
      run_id: "overview-run",
      asset_id: "c2",
      sensor_id: "s2",
      kind: "MISSING",
      origin: "DATA_QUALITY",
      state: "RESOLVED",
      first_tick: 2,
      last_tick: 8,
    },
  ],
  connection_status: "CONNECTED",
};
afterEach(cleanup);
it("never invents health metrics before a run starts", () => {
  render(<SystemOverview />);
  expect(screen.getByText("Awaiting simulation")).toBeInTheDocument();
  expect(screen.queryByText("99.2%")).not.toBeInTheDocument();
});
it("derives quality from actual observations and filters alerts", () => {
  labStore.setRunSnapshot(snapshot);
  labStore.setConnectionStatus("CONNECTED");
  render(<SystemOverview />);
  expect(screen.getByText("50.0%")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open alerts" }));
  const table = screen.getByRole("table", { name: "Simulation alerts" });
  expect(within(table).queryByText("c2")).not.toBeInTheDocument();
  fireEvent.click(within(table).getByRole("button", { name: /Above limit/ }));
  expect(labStore.getState().selection.selectedId).toBe("c1");
  expect(
    screen.getByRole("heading", { name: "Alert Details" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Investigate alert" }));
  expect(labStore.getState().editor.mode).toBe("INVESTIGATE");
});
it("collects real samples, clears charts on a new run, and marks stale streams", () => {
  labStore.setRunSnapshot(snapshot);
  render(<SystemOverview />);
  act(() => labStore.setRunSnapshot({ ...snapshot, tick: 40 }));
  expect(
    screen.getByRole("img", { name: /Mean pressure history/ }),
  ).toBeInTheDocument();
  act(() =>
    labStore.setRunSnapshot({
      ...snapshot,
      run_id: "new-run",
      tick: 0,
      alerts: [],
    }),
  );
  expect(
    screen.queryByRole("img", { name: /Mean pressure history/ }),
  ).not.toBeInTheDocument();
  act(() => labStore.setConnectionStatus("STALE"));
  expect(
    screen.getByText("Stream stale · last received values"),
  ).toBeInTheDocument();
});

it("keeps reverse-flow values inside the chart instead of clipping below its axis", () => {
  labStore.setRunSnapshot({
    ...snapshot,
    run_id: "reverse-flow",
    physical: { ...snapshot.physical, flows_kg_s: { p1: -0.4 } },
  });
  render(<SystemOverview />);
  act(() =>
    labStore.setRunSnapshot({
      ...snapshot,
      run_id: "reverse-flow",
      tick: 40,
      physical: { ...snapshot.physical, flows_kg_s: { p1: -0.2 } },
    }),
  );
  const chart = screen.getByRole("img", { name: /Mean flow history/ });
  const path = chart.querySelector("path")?.getAttribute("d") ?? "";
  const coordinates = [...path.matchAll(/[ML]([\d.]+) ([\d.-]+)/g)].map(
    (match) => Number(match[2]),
  );
  expect(coordinates).toHaveLength(2);
  expect(coordinates.every((y) => y >= 16 && y <= 80)).toBe(true);
});
