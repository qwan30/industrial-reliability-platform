import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EquipmentCatalog } from "../EquipmentCatalog";
import { labStore } from "../store";
import type { LabDefinition } from "../types";
import { validateLabRevision } from "../api";

vi.mock("../api", () => ({ validateLabRevision: vi.fn() }));
const lab: LabDefinition = {
  schema_version: "lab-definition-v1",
  lab_id: "lab-1",
  revision: 2,
  name: "Reference Lab",
  scene_revision: "v1",
  assets: [
    {
      asset_id: "compressor-1",
      type: "COMPRESSOR",
      position_m: [2, 0, 3],
      rotation_y_rad: 0,
      parameters: {},
    },
    {
      asset_id: "tank-1",
      type: "TANK",
      position_m: [5, 0, 3],
      rotation_y_rad: 0,
      parameters: {},
    },
  ],
  pipes: [],
  sensors: [],
};
beforeEach(() => {
  labStore.setLab(lab);
  labStore.clearSelection();
  labStore.setMode("OPERATE");
  vi.clearAllMocks();
});
afterEach(cleanup);
describe("EquipmentCatalog", () => {
  it("searches equipment by name and selects the real asset", () => {
    render(<EquipmentCatalog />);
    fireEvent.change(
      screen.getByRole("searchbox", { name: "Search equipment" }),
      { target: { value: "receiver" } },
    );
    expect(
      screen.queryByRole("button", { name: /Select Compressor/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Select Air Receiver Tank/ }),
    );
    expect(labStore.getState().selection.selectedId).toBe("tank-1");
    expect(labStore.getState().camera.focusTarget).toEqual([5, 0, 3]);
  });
  it("shows an actionable no-results state and clears the query", () => {
    render(<EquipmentCatalog />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "not-present" },
    });
    expect(screen.getByText("No matching equipment")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(
      screen.getByRole("button", { name: /Select Compressor/ }),
    ).toBeInTheDocument();
  });
  it("validates the current revision and displays the actual result", async () => {
    vi.mocked(validateLabRevision).mockResolvedValue({
      run_eligible: true,
      errors: [],
      definition_digest: "x",
      model_version: "1",
    });
    render(<EquipmentCatalog />);
    fireEvent.click(screen.getByRole("button", { name: "Validate topology" }));
    expect(
      await screen.findByText("Topology valid · ready to run"),
    ).toBeInTheDocument();
    expect(validateLabRevision).toHaveBeenCalledWith("lab-1", 2);
  });
  it("shows validation errors rather than claiming success", async () => {
    vi.mocked(validateLabRevision).mockRejectedValue(
      new Error("Backend unavailable"),
    );
    render(<EquipmentCatalog />);
    fireEvent.click(screen.getByRole("button", { name: "Validate topology" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Backend unavailable",
    );
  });
  it("opens Build without pretending to commit an unchanged revision", () => {
    render(<EquipmentCatalog />);
    fireEvent.click(screen.getByRole("button", { name: "Edit lab" }));
    expect(labStore.getState().editor.mode).toBe("BUILD");
  });
});
