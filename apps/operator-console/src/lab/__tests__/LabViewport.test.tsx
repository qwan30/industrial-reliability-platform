import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { LabViewport } from "../LabViewport";
import { labStore } from "../store";
vi.mock("../LabScene", () => ({ LabScene: () => <div>Live 3D scene</div> }));
beforeEach(() => {
  labStore.setLab({
    lab_id: "1",
    revision: 1,
    name: "Test",
    scene_revision: "1",
    schema_version: "1",
    assets: [
      {
        asset_id: "comp-1",
        type: "COMPRESSOR",
        position_m: [0, 0, 0],
        rotation_y_rad: 0,
        parameters: {},
      },
    ],
    pipes: [],
    sensors: [],
  });
  labStore.clearSelection();
  labStore.setCameraMode("ORBIT");
});
afterEach(cleanup);
it("switches from 3D to a selectable topology and back", () => {
  render(<LabViewport />);
  expect(screen.getByText("Live 3D scene")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Topology" }));
  expect(
    screen.getByRole("img", { name: "Lab connectivity diagram" }),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Select comp-1" }));
  expect(labStore.getState().selection.selectedId).toBe("comp-1");
  fireEvent.click(screen.getByRole("button", { name: "3D Twin" }));
  expect(screen.getByText("Live 3D scene")).toBeVisible();
});
it("switches camera modes with accessible controls", () => {
  render(<LabViewport />);
  fireEvent.click(screen.getByRole("button", { name: "Walk camera" }));
  expect(labStore.getState().camera.mode).toBe("WALK");
  fireEvent.click(screen.getByRole("button", { name: "Orbit camera" }));
  expect(labStore.getState().camera.mode).toBe("ORBIT");
});
