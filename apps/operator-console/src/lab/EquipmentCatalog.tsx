import { useState } from "react";
import { validateLabRevision } from "./api";
import { LabIcon, type LabIconName } from "./LabIcon";
import { ObjectTree } from "./ObjectTree";
import { labStore, useEditorSlice, useSelectionSlice } from "./store";
import type { AssetType } from "./types";

export const EQUIPMENT_LABELS: Record<
  AssetType,
  { label: string; description: string; icon: LabIconName }
> = {
  COMPRESSOR: {
    label: "Compressor",
    description: "Rotary air source",
    icon: "compressor",
  },
  TANK: {
    label: "Air Receiver Tank",
    description: "Pressure storage buffer",
    icon: "tank",
  },
  ISOLATION_VALVE: {
    label: "Isolation Valve",
    description: "Quarter-turn isolation",
    icon: "valve",
  },
  CONTROL_VALVE: {
    label: "Control Valve",
    description: "Pneumatic modulating valve",
    icon: "valve",
  },
  DEMAND: {
    label: "Pneumatic Load",
    description: "Factory consumption branch",
    icon: "load",
  },
};

export function EquipmentCatalog() {
  const { lab, isDirty } = useEditorSlice();
  const { selectedId } = useSelectionSlice();
  const [tab, setTab] = useState<"catalog" | "topology">("catalog");
  const [query, setQuery] = useState("");
  const [validation, setValidation] = useState<{
    revision: number;
    text: string;
    error: boolean;
  } | null>(null);
  const [validating, setValidating] = useState(false);
  if (!lab) return null;
  const term = query.trim().toLowerCase();
  const assets = lab.assets.filter((asset) =>
    `${EQUIPMENT_LABELS[asset.type].label} ${asset.type} ${asset.asset_id}`
      .toLowerCase()
      .includes(term),
  );
  const pipes = lab.pipes.filter((pipe) =>
    `pipes fittings ${pipe.pipe_id}`.toLowerCase().includes(term),
  );
  const sensors = lab.sensors.filter((sensor) =>
    `sensors ${sensor.kind} ${sensor.sensor_id}`.toLowerCase().includes(term),
  );

  async function validate() {
    if (!lab) return;
    setValidating(true);
    setValidation(null);
    try {
      const result = await validateLabRevision(lab.lab_id, lab.revision);
      setValidation({
        revision: lab.revision,
        error: !result.run_eligible,
        text: result.run_eligible
          ? "Topology valid · ready to run"
          : result.errors.map((error) => error.message).join(" · ") ||
            "Topology is not run-eligible",
      });
    } catch (error) {
      setValidation({
        revision: lab.revision,
        error: true,
        text:
          error instanceof Error
            ? error.message
            : "Unable to validate topology",
      });
    } finally {
      setValidating(false);
    }
  }

  return (
    <aside className="equipment-catalog" aria-label="Equipment catalog">
      <div
        className="workspace-tabs"
        role="group"
        aria-label="Equipment navigation"
      >
        <button
          type="button"
          className={tab === "catalog" ? "active" : ""}
          aria-pressed={tab === "catalog"}
          onClick={() => setTab("catalog")}
        >
          Catalog
        </button>
        <button
          type="button"
          className={tab === "topology" ? "active" : ""}
          aria-pressed={tab === "topology"}
          onClick={() => setTab("topology")}
        >
          Topology
        </button>
      </div>
      {tab === "catalog" ? (
        <>
          <div className="catalog-search">
            <LabIcon name="search" size={16} />
            <input
              type="search"
              aria-label="Search equipment"
              placeholder="Search equipment…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <div className="equipment-scroll">
            {assets.length > 0 && (
              <details open className="equipment-group">
                <summary>
                  Pneumatic Components <span>{assets.length}</span>
                </summary>
                {assets.map((asset) => {
                  const info = EQUIPMENT_LABELS[asset.type];
                  return (
                    <button
                      type="button"
                      key={asset.asset_id}
                      className={`equipment-entry ${selectedId === asset.asset_id ? "selected" : ""}`}
                      aria-label={`Select ${info.label} ${asset.asset_id}`}
                      aria-pressed={selectedId === asset.asset_id}
                      onClick={() => {
                        labStore.selectEntity(asset.asset_id, "ASSET");
                        labStore.focusOn(asset.position_m);
                      }}
                    >
                      <LabIcon name={info.icon} size={23} />
                      <span>
                        <strong>{info.label}</strong>
                        <small title={asset.asset_id}>{asset.asset_id}</small>
                      </span>
                      <LabIcon name="chevron" size={12} />
                    </button>
                  );
                })}
              </details>
            )}
            {pipes.length > 0 && (
              <details
                className="equipment-group"
                open={term ? true : undefined}
              >
                <summary>
                  Pipes & Fittings <span>{pipes.length}</span>
                </summary>
                {pipes.map((pipe) => (
                  <button
                    type="button"
                    key={pipe.pipe_id}
                    className={`equipment-entry ${selectedId === pipe.pipe_id ? "selected" : ""}`}
                    onClick={() => labStore.selectEntity(pipe.pipe_id, "PIPE")}
                  >
                    <LabIcon name="pipe" size={23} />
                    <span>
                      <strong>{pipe.pipe_id}</strong>
                      <small>
                        {pipe.from_port.port} → {pipe.to_port.port}
                      </small>
                    </span>
                  </button>
                ))}
              </details>
            )}
            {sensors.length > 0 && (
              <details
                className="equipment-group"
                open={term ? true : undefined}
              >
                <summary>
                  Instrumentation <span>{sensors.length}</span>
                </summary>
                {sensors.map((sensor) => (
                  <button
                    type="button"
                    key={sensor.sensor_id}
                    className={`equipment-entry ${selectedId === sensor.sensor_id ? "selected" : ""}`}
                    onClick={() =>
                      labStore.selectEntity(sensor.sensor_id, "SENSOR")
                    }
                  >
                    <LabIcon name="sensor" size={23} />
                    <span>
                      <strong>
                        {sensor.kind === "PRESSURE"
                          ? "Pressure Sensor"
                          : "Flow Sensor"}
                      </strong>
                      <small>{sensor.sensor_id}</small>
                    </span>
                  </button>
                ))}
              </details>
            )}
            {!assets.length && !pipes.length && !sensors.length && (
              <div className="catalog-empty">
                <LabIcon name="search" size={26} />
                <strong>
                  {term ? "No matching equipment" : "Your lab is empty"}
                </strong>
                <p>
                  {term
                    ? "Try an equipment name or asset ID."
                    : "Switch to Build to place your first component."}
                </p>
                {term && (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => setQuery("")}
                  >
                    Clear search
                  </button>
                )}
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="catalog-tree">
          <ObjectTree />
        </div>
      )}
      <div className="catalog-revision">
        <strong>Lab Revision</strong>
        <div className="revision-meta">
          <LabIcon name="check" size={17} />
          <b>v{lab.revision}</b>
          <span>{isDirty ? "Unsaved changes" : "Saved definition"}</span>
        </div>
        {validation?.revision === lab.revision && (
          <p
            className={`validation-feedback ${validation.error ? "is-error" : ""}`}
            role={validation.error ? "alert" : "status"}
          >
            {validation.text}
          </p>
        )}
        <div className="revision-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => labStore.setMode("BUILD")}
          >
            Edit lab
          </button>
          <button
            type="button"
            className="btn btn-sm"
            disabled={validating || isDirty}
            onClick={validate}
          >
            {validating ? "Validating…" : "Validate topology"}
          </button>
        </div>
      </div>
    </aside>
  );
}
