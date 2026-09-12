import { Html } from "@react-three/drei";
import { EQUIPMENT_LABELS } from "./EquipmentCatalog";
import {
  labStore,
  useConnectionSlice,
  useEditorSlice,
  useRunSlice,
  useSelectionSlice,
} from "./store";
import type { AssetType } from "./types";

const CALLOUT_TYPES: AssetType[] = [
  "COMPRESSOR",
  "TANK",
  "CONTROL_VALVE",
  "DEMAND",
];

/** A small representative set keeps the plant legible instead of labelling every mesh. */
export function SceneCallouts() {
  const { lab, mode } = useEditorSlice();
  const { snapshot } = useRunSlice();
  const { selectedId } = useSelectionSlice();
  const { status } = useConnectionSlice();
  if (!lab || mode !== "OPERATE") return null;
  return (
    <>
      {CALLOUT_TYPES.map((type, index) => {
        const candidates = lab.assets.filter((asset) => asset.type === type);
        const asset = candidates[Math.min(index, candidates.length - 1)];
        if (!asset) return null;
        const pressure = snapshot?.physical.pressures_pa[asset.asset_id];
        const available = pressure !== undefined && Number.isFinite(pressure);
        return (
          <Html
            key={asset.asset_id}
            position={[
              asset.position_m[0],
              asset.position_m[1] + 2.3,
              asset.position_m[2],
            ]}
            center
            zIndexRange={[2, 0]}
            style={{ pointerEvents: "none" }}
          >
            <button
              type="button"
              className="scene-callout"
              data-selected={selectedId === asset.asset_id}
              data-kind={type}
              aria-label={`Inspect ${EQUIPMENT_LABELS[type].label} ${asset.asset_id}`}
              onClick={() => {
                labStore.selectEntity(asset.asset_id, "ASSET");
                labStore.focusOn(asset.position_m);
              }}
            >
              <span
                className={`status-dot ${available ? status.toLowerCase() : "disconnected"}`}
              />
              <span>
                <strong>{EQUIPMENT_LABELS[type].label}</strong>
                <small>
                  {available
                    ? `${(pressure / 100000).toFixed(2)} bar${status !== "CONNECTED" ? " · last" : ""}`
                    : "Awaiting telemetry"}
                </small>
              </span>
            </button>
          </Html>
        );
      })}
    </>
  );
}
