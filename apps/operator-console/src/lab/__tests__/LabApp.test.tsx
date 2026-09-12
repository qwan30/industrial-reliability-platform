import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { LabApp } from "../LabApp";
import { labStore } from "../store";
import { createLab, getReferenceTemplate, getLab } from "../api";
import type { LabDefinition } from "../types";

vi.mock("../LabScene", () => ({ LabScene: () => <div>3D scene</div> }));
vi.mock("../useLabStream", () => ({ useLabStream: () => undefined }));
vi.mock("../api", () => ({
  getReferenceTemplate: vi.fn(),
  createLab: vi.fn(),
  getLab: vi.fn(),
  getRunHistory: vi.fn().mockResolvedValue([]),
  validateLabRevision: vi.fn(),
  updateLab: vi.fn(),
}));

const reference: LabDefinition = {
  lab_id: "ref",
  revision: 1,
  name: "Reference Pneumatic Lab",
  schema_version: "1",
  scene_revision: "1",
  assets: [
    {
      asset_id: "comp-1",
      type: "COMPRESSOR",
      parameters: {},
      position_m: [-8, 0, -4.5],
      rotation_y_rad: 0,
    },
    {
      asset_id: "tank-1",
      type: "TANK",
      parameters: {},
      position_m: [-4, 0, -4.5],
      rotation_y_rad: 0,
    },
  ],
  pipes: [],
  sensors: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  labStore.setLab(null);
  labStore.setMode("OPERATE");
  labStore.clearSelection();
  vi.mocked(getReferenceTemplate).mockResolvedValue(reference);
});

afterEach(cleanup);

it("retries failed initialization without leaving an empty workspace", async () => {
  vi.mocked(getReferenceTemplate).mockRejectedValueOnce(
    new Error("API unavailable"),
  );
  render(<LabApp />);
  expect(await screen.findByRole("alert")).toHaveTextContent("API unavailable");
  fireEvent.click(screen.getByRole("button", { name: "Retry loading lab" }));
  expect(
    await screen.findByRole("heading", { name: "System Overview" }),
  ).toBeInTheDocument();
});

it("keeps a newly created blank lab instead of restoring stale undo history", async () => {
  vi.mocked(createLab).mockResolvedValue({
    ...reference,
    lab_id: "blank",
    name: "Blank Industrial Lab",
    assets: [],
  });
  render(<LabApp />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Start Blank Lab" }),
  );
  await waitFor(() =>
    expect(labStore.getState().editor.lab?.lab_id).toBe("blank"),
  );
  expect(labStore.getState().editor.lab?.assets).toHaveLength(0);
  expect(labStore.getState().editor.mode).toBe("BUILD");
});

it("keeps add, undo and redo working in the docked Build palette", async () => {
  render(<LabApp />);
  await screen.findByRole("heading", { name: "System Overview" });
  fireEvent.click(screen.getByRole("tab", { name: "Build" }));
  fireEvent.click(screen.getAllByRole("button", { name: /Place in Scene/ })[0]);
  await waitFor(() =>
    expect(labStore.getState().editor.lab?.assets).toHaveLength(3),
  );
  expect(labStore.getState().editor.isDirty).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: /Undo/ }));
  await waitFor(() =>
    expect(labStore.getState().editor.lab?.assets).toHaveLength(2),
  );
  fireEvent.click(screen.getByRole("button", { name: /Redo/ }));
  await waitFor(() =>
    expect(labStore.getState().editor.lab?.assets).toHaveLength(3),
  );
});

it("places subsequent assets at distinct non-overlapping positions on the floor", async () => {
  render(<LabApp />);
  await screen.findByRole("heading", { name: "System Overview" });
  fireEvent.click(screen.getByRole("tab", { name: "Build" }));

  // Place asset 1
  fireEvent.click(screen.getAllByRole("button", { name: /Place in Scene/ })[0]);
  await waitFor(() =>
    expect(labStore.getState().editor.lab?.assets).toHaveLength(3),
  );
  const asset1 = labStore.getState().editor.lab!.assets[2];

  // Place asset 2
  fireEvent.click(screen.getAllByRole("button", { name: /Place in Scene/ })[1]);
  await waitFor(() =>
    expect(labStore.getState().editor.lab?.assets).toHaveLength(4),
  );
  const asset2 = labStore.getState().editor.lab!.assets[3];

  // Positions MUST NOT be identical!
  const pos1 = `${asset1.position_m[0]},${asset1.position_m[2]}`;
  const pos2 = `${asset2.position_m[0]},${asset2.position_m[2]}`;
  expect(pos1).not.toBe(pos2);
});

it("provides a lab switcher to return to Reference Lab from a blank lab", async () => {
  // Simulate starting in a saved blank lab
  localStorage.setItem("irp.lastLabId", "blank-custom");
  const blankLab: LabDefinition = {
    ...reference,
    lab_id: "blank-custom",
    name: "Blank Industrial Lab",
    assets: [],
  };
  vi.mocked(getLab).mockResolvedValue(blankLab);

  render(<LabApp />);
  await waitFor(() =>
    expect(labStore.getState().editor.lab?.name).toBe("Blank Industrial Lab"),
  );

  // Open Lab Switcher menu in toolbar
  const switcher = await screen.findByRole("button", { name: /Switch lab/ });
  fireEvent.click(switcher);

  // Click Load Reference Lab option
  const loadRefBtn = screen.getByRole("button", { name: /Load Reference Lab/ });
  fireEvent.click(loadRefBtn);

  await waitFor(() =>
    expect(labStore.getState().editor.lab?.name).toBe(
      "Reference Pneumatic Lab",
    ),
  );
  expect(labStore.getState().editor.lab?.assets).toHaveLength(2);
});

it("retains collected telemetry when returning from Investigate", async () => {
  render(<LabApp />);
  await screen.findByRole("heading", { name: "System Overview" });
  const frame = {
    run_id: "navigation-run",
    tick: 10,
    status: "RUNNING",
    control_revision: 0,
    event_sequence: 0,
    physical: {
      tick: 10,
      pressures_pa: { c1: 800000 },
      flows_kg_s: {},
      operating_modes: {},
    },
    observations: [],
    pending_commands: [],
    alerts: [],
    connection_status: "CONNECTED",
  };
  await act(async () => {
    labStore.setRunSnapshot(frame);
  });
  await act(async () => {
    labStore.setRunSnapshot({ ...frame, tick: 20 });
  });
  expect(
    screen.getByRole("img", { name: /Mean pressure history/ }),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("tab", { name: "Investigate" }));
  fireEvent.click(screen.getByRole("tab", { name: "Operate" }));
  expect(
    screen.getByRole("img", { name: /Mean pressure history/ }),
  ).toBeVisible();
});
