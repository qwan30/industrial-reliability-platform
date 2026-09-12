import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SceneCallouts } from "../SceneCallouts";
import { labStore } from "../store";
vi.mock("@react-three/drei", () => ({
  Html: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
beforeEach(() => {
  labStore.setMode("OPERATE");
  labStore.clearSelection();
  labStore.setLab({
    lab_id: "callout",
    name: "Lab",
    revision: 1,
    schema_version: "1",
    scene_revision: "1",
    assets: [
      {
        asset_id: "c1",
        type: "COMPRESSOR",
        position_m: [1, 0, 2],
        rotation_y_rad: 0,
        parameters: {},
      },
    ],
    pipes: [],
    sensors: [],
  });
});
afterEach(cleanup);
it("labels equipment without inventing telemetry and allows selection", () => {
  render(<SceneCallouts />);
  expect(screen.getByText("Awaiting telemetry")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect Compressor c1" }),
  );
  expect(labStore.getState().selection.selectedId).toBe("c1");
});
it("does not cover port authoring controls in Build", () => {
  labStore.setMode("BUILD");
  render(<SceneCallouts />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
