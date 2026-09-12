import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RunControls } from "../RunControls";
import { createRun } from "../api";
import { labStore } from "../store";
import type { RunSnapshot } from "../types";
vi.mock("../api", () => ({ createRun: vi.fn(), submitCommand: vi.fn() }));
const snapshot: RunSnapshot = {
  run_id: "old",
  tick: 0,
  status: "STOPPED",
  control_revision: 0,
  event_sequence: 0,
  physical: { tick: 0, pressures_pa: {}, flows_kg_s: {}, operating_modes: {} },
  observations: [],
  pending_commands: [],
  alerts: [],
  connection_status: "CONNECTED",
};
beforeEach(() => {
  vi.clearAllMocks();
  labStore.setLab({
    lab_id: "lab",
    name: "Lab",
    revision: 1,
    assets: [],
    pipes: [],
    sensors: [],
    scene_revision: "1",
    schema_version: "1",
  });
  labStore.setRunSnapshot(snapshot);
});
afterEach(cleanup);
it("honors CREATED from the API instead of claiming the worker is running", async () => {
  vi.mocked(createRun).mockResolvedValue({
    run_id: "new",
    status: "CREATED",
    snapshot_url: "",
    stream_url: "",
  });
  render(<RunControls />);
  fireEvent.click(screen.getByRole("button", { name: "Start Run" }));
  await waitFor(() => expect(labStore.getState().run.status).toBe("CREATED"));
  expect(screen.getByRole("status")).toHaveTextContent(
    "Waiting for simulation worker",
  );
});
it("allows a fresh run after a terminal state", () => {
  labStore.setRunSnapshot({ ...snapshot, status: "COMPLETED" });
  render(<RunControls />);
  expect(screen.getByRole("button", { name: "Start Run" })).toBeEnabled();
});
it("does not offer local-only speed changes for an active run", () => {
  render(<RunControls />);
  act(() => labStore.setRunSnapshot({ ...snapshot, status: "RUNNING" }));
  expect(screen.getByRole("button", { name: "10x" })).toBeDisabled();
});
