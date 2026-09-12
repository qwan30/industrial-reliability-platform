import { useState } from "react";
import {
  useEditorSlice,
  useConnectionSlice,
  labStore,
  type LabMode,
} from "./store";
import { LabIcon } from "./LabIcon";
import { createLab, getReferenceTemplate } from "./api";

export function LabToolbar() {
  const { lab, mode } = useEditorSlice();
  const { status } = useConnectionSlice();
  const [showHelp, setShowHelp] = useState(false);
  const [showLabSwitcher, setShowLabSwitcher] = useState(false);
  const modes: LabMode[] = ["BUILD", "OPERATE", "INVESTIGATE"];

  const hasOverlappingAssets = (() => {
    if (!lab || lab.assets.length < 2) return false;
    const seen = new Set<string>();
    for (const a of lab.assets) {
      const key = `${a.position_m[0].toFixed(1)},${a.position_m[2].toFixed(1)}`;
      if (seen.has(key)) return true;
      seen.add(key);
    }
    return false;
  })();

  return (
    <header className="lab-toolbar">
      <div className="toolbar-left">
        <div className="brand-logo">
          <span className="logo-icon">
            <LabIcon name="cube" size={36} />
          </span>
          <div>
            <h1 className="logo-title">Virtual Lab</h1>
            <span className="logo-subtitle">
              Industrial Digital Twin Platform
            </span>
          </div>
        </div>

        <div className="lab-switcher-wrapper">
          <button
            type="button"
            className="lab-badge lab-switcher-btn"
            aria-label={`Switch lab: ${lab?.name ?? "Loading workspace"}`}
            aria-haspopup="true"
            aria-expanded={showLabSwitcher}
            onClick={() => setShowLabSwitcher(!showLabSwitcher)}
          >
            <span className="lab-name">{lab?.name ?? "Loading workspace"}</span>
            {lab && <span className="lab-rev">v{lab.revision}</span>}
            <span className="switcher-caret" aria-hidden="true">
              ▾
            </span>
          </button>

          {showLabSwitcher && (
            <div
              className="lab-switcher-dropdown"
              role="menu"
              onKeyDown={(e) => {
                if (e.key === "Escape") setShowLabSwitcher(false);
              }}
            >
              <div className="switcher-header">
                <strong>Workspace Environments</strong>
                <span>Switch between reference setup and custom models</span>
              </div>

              <div className="switcher-card">
                <div className="switcher-card-info">
                  <strong>Reference Pneumatic Lab</strong>
                  <p>
                    Standard 4-train system (20 assets, 18 pipes, 20 sensors)
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  onClick={async () => {
                    setShowLabSwitcher(false);
                    try {
                      const refLab = await getReferenceTemplate();
                      labStore.setLab(refLab);
                      localStorage.removeItem("irp.lastLabId");
                      labStore.setMode("OPERATE");
                      const firstComp = refLab.assets.find(
                        (a) => a.type === "COMPRESSOR",
                      );
                      if (firstComp) {
                        labStore.selectEntity(firstComp.asset_id, "ASSET");
                      }
                    } catch (e) {
                      console.error("Failed to load reference lab:", e);
                    }
                  }}
                >
                  Load Reference Lab
                </button>
              </div>

              <div className="switcher-card">
                <div className="switcher-card-info">
                  <strong>Blank Industrial Lab</strong>
                  <p>Clean training room floor for custom system authoring</p>
                </div>
                <button
                  type="button"
                  className="btn btn-sm btn-secondary"
                  onClick={async () => {
                    setShowLabSwitcher(false);
                    try {
                      const blank = await createLab(
                        "Blank Industrial Lab",
                        "BLANK",
                      );
                      labStore.setLab(blank);
                      labStore.clearSelection();
                      localStorage.setItem("irp.lastLabId", blank.lab_id);
                      labStore.setMode("BUILD");
                    } catch (e) {
                      console.error("Failed to create blank lab:", e);
                    }
                  }}
                >
                  Create Blank Lab
                </button>
              </div>

              {hasOverlappingAssets && (
                <div className="switcher-card switcher-arrange-card">
                  <div className="switcher-card-info">
                    <strong style={{ color: "var(--lab-warning)" }}>
                      Stacked Equipment ({lab?.assets.length ?? 0} items)
                    </strong>
                    <p>
                      Assets share identical coordinates. Auto-arrange across
                      the floor grid.
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    onClick={() => {
                      setShowLabSwitcher(false);
                      window.dispatchEvent(
                        new CustomEvent("irp:arrange-assets"),
                      );
                    }}
                  >
                    Auto-arrange on Grid
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <nav className="toolbar-center" aria-label="Lab workspace">
        <div
          className="mode-segmented-control"
          role="tablist"
          aria-label="Workspace mode"
        >
          {modes.map((item, index) => (
            <button
              key={item}
              type="button"
              role="tab"
              id={`mode-${item.toLowerCase()}`}
              aria-controls="lab-workspace"
              aria-selected={mode === item}
              tabIndex={mode === item ? 0 : -1}
              className={`mode-btn ${mode === item ? "active" : ""}`}
              onClick={() => labStore.setMode(item)}
              onKeyDown={(event) => {
                if (
                  !["ArrowRight", "ArrowLeft", "Home", "End"].includes(
                    event.key,
                  )
                )
                  return;
                event.preventDefault();
                const next =
                  event.key === "Home"
                    ? modes[0]
                    : event.key === "End"
                      ? modes[2]
                      : modes[
                          (index + (event.key === "ArrowRight" ? 1 : 2)) % 3
                        ];
                labStore.setMode(next);
                document.getElementById(`mode-${next.toLowerCase()}`)?.focus();
              }}
            >
              {item[0]}
              {item.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </nav>

      <div className="toolbar-right">
        <div
          className="connection-indicator"
          title={`Simulation stream: ${status}`}
        >
          <span className={`status-dot ${status.toLowerCase()}`} />
          <span>
            {status === "CONNECTED"
              ? "Online"
              : status === "CONNECTING"
                ? "Connecting"
                : status === "STALE"
                  ? "Stream stale"
                  : "Offline"}
          </span>
        </div>

        <div className="toolbar-help">
          <button
            type="button"
            className="btn-icon"
            aria-label="Workspace help"
            aria-expanded={showHelp}
            aria-controls="workspace-help"
            onClick={() => setShowHelp(!showHelp)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setShowHelp(false);
            }}
          >
            <LabIcon name="help" size={19} />
          </button>
          {showHelp && (
            <div
              id="workspace-help"
              className="workspace-help"
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setShowHelp(false);
                  (
                    event.currentTarget.previousElementSibling as HTMLElement
                  )?.focus();
                }
              }}
            >
              <strong>Navigate your digital twin</strong>
              <p>
                Build to edit your lab. Operate to run simulations. Investigate
                to compare runs and inject faults.
              </p>
              <dl>
                <dt>Orbit</dt>
                <dd>Drag · Scroll to zoom</dd>
                <dt>Walk</dt>
                <dd>W A S D</dd>
                <dt>Reset view</dt>
                <dd>H</dd>
                <dt>Focus selected</dt>
                <dd>F</dd>
              </dl>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setShowHelp(false)}
              >
                Got it
              </button>
            </div>
          )}
        </div>

        <span className="workspace-avatar" title="Local simulation workspace">
          <LabIcon name="cube" size={18} />
        </span>
      </div>
    </header>
  );
}
