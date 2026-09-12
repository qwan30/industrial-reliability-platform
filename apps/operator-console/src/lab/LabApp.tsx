import { useEffect, useState, useRef } from "react";
import { LabToolbar } from "./LabToolbar";
import { LabViewport } from "./LabViewport";
import { EquipmentCatalog } from "./EquipmentCatalog";
import { SystemOverview } from "./SystemOverview";
import { LabStatusBar } from "./LabStatusBar";
import { LabIcon } from "./LabIcon";
import { Inspector } from "./Inspector";
import { RunControls } from "./RunControls";
import { Timeline } from "./Timeline";
import { useLabStream } from "./useLabStream";
import { BuilderPanel } from "./BuilderPanel";
import { ExperimentPanel } from "./ExperimentPanel";
import { RunComparison } from "./RunComparison";
import { IncidentInspector } from "./IncidentInspector";
import { BaselinePanel } from "./BaselinePanel";
import { useEditorSlice } from "./store";
import {
  editorReducer,
  initialEditorState,
  type EditorAction,
} from "./editorReducer";
import { useRunSlice, labStore } from "./store";
import { getReferenceTemplate, createLab, getLab } from "./api";
import { useResizablePanels } from "./useResizablePanels";
import "./lab.css";
import "./workspace.css";

function getNextAssetPosition(
  existingAssets: Array<{ position_m: [number, number, number] }>,
): [number, number, number] {
  const occupied = new Set(
    existingAssets.map(
      (a) => `${a.position_m[0].toFixed(1)},${a.position_m[2].toFixed(1)}`,
    ),
  );
  // Grid slots across factory room floor (24x16m room: X from -9 to +9, Z from -5 to +5)
  for (let z = -5.0; z <= 5.0; z += 2.5) {
    for (let x = -9.0; x <= 9.0; x += 3.0) {
      const key = `${x.toFixed(1)},${z.toFixed(1)}`;
      if (!occupied.has(key)) {
        return [x, 0, z];
      }
    }
  }
  const i = existingAssets.length;
  const col = i % 7;
  const row = Math.floor(i / 7) % 5;
  return [-9.0 + col * 2.8, 0, -5.0 + row * 2.4];
}

export function LabApp({ onReplay }: { onReplay?: () => void } = {}) {
  const { runId } = useRunSlice();
  const { lab, mode } = useEditorSlice();
  const workspaceRef = useRef<HTMLElement | null>(null);

  const [editorHistory, setEditorHistory] = useState(() =>
    initialEditorState(),
  );

  // External loads/saves reset undo history; editor commands synchronously update the draft.
  const historyState =
    editorHistory.present === lab ? editorHistory : initialEditorState(lab);
  const dispatchHistory = (action: EditorAction) => {
    const next = editorReducer(historyState, action);
    setEditorHistory(next);
    if (next.present && next.present !== lab) {
      labStore.updateLabDraft(() => next.present!);
    }
  };

  const [isFirstUse, setIsFirstUse] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [initAttempt, setInitAttempt] = useState(0);
  const [creatingBlank, setCreatingBlank] = useState(false);
  const [investigateTab, setInvestigateTab] = useState<
    "EXPERIMENT" | "COMPARE" | "BASELINE"
  >("EXPERIMENT");

  // Dynamic resizable sidebars with collapse thresholds and edge-drag/click support
  const {
    leftWidth,
    rightWidth,
    isLeftCollapsed,
    isRightCollapsed,
    isResizing,
    startLeftResize,
    startRightResize,
    toggleLeftCollapse,
    toggleRightCollapse,
    expandLeft,
    expandRight,
    handleLeftKeyDown,
    handleRightKeyDown,
  } = useResizablePanels({
    initialLeftWidth: 260,
    minLeftWidth: 180,
    maxLeftWidth: 480,
    collapseLeftThreshold: 130,

    initialRightWidth: 560,
    minRightWidth: 360,
    maxRightWidth: 880,
    collapseRightThreshold: 200,

    containerRef: workspaceRef,
  });

  useEffect(() => {
    const handleArrange = () => {
      dispatchHistory({ type: "ARRANGE_ASSETS" });
    };
    window.addEventListener("irp:arrange-assets", handleArrange);
    return () =>
      window.removeEventListener("irp:arrange-assets", handleArrange);
  }, [historyState]);

  useLabStream(runId);

  useEffect(() => {
    async function initLab() {
      setLoading(true);
      setLoadError(null);
      try {
        const savedLabId = localStorage.getItem("irp.lastLabId");
        if (savedLabId) {
          try {
            const existingLab = await getLab(savedLabId);
            labStore.setLab(existingLab);
            setIsFirstUse(false);
            setLoading(false);
            return;
          } catch {
            // If stored lab not found, fall back to reference
          }
        }

        // Fetch reference template
        const refLab = await getReferenceTemplate();
        labStore.setLab(refLab);

        // Auto-select the first compressor
        const firstComp = refLab.assets.find((a) => a.type === "COMPRESSOR");
        if (firstComp) {
          labStore.selectEntity(firstComp.asset_id, "ASSET");
        }
      } catch (err) {
        setLoadError(
          err instanceof Error
            ? err.message
            : "Unable to load the reference lab.",
        );
      } finally {
        setLoading(false);
      }
    }

    initLab();
  }, [initAttempt]);

  const handleRunReference = async () => {
    setIsFirstUse(false);
    labStore.setMode("OPERATE");
  };

  const handleStartBlank = async () => {
    setCreatingBlank(true);
    setLoadError(null);
    try {
      const blank = await createLab("Blank Industrial Lab", "BLANK");
      labStore.setLab(blank);
      labStore.clearSelection();
      localStorage.setItem("irp.lastLabId", blank.lab_id);
      setIsFirstUse(false);
      labStore.setMode("BUILD");
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Unable to create a blank lab.",
      );
    } finally {
      setCreatingBlank(false);
    }
  };

  if (loading || !lab) {
    return (
      <div className="lab-app-container">
        <LabToolbar />
        <main className="workspace-loading" aria-busy={loading}>
          <LabIcon name="cube" size={48} />
          <h2>
            {loading ? "Preparing your digital twin" : "Workspace unavailable"}
          </h2>
          {loading ? (
            <>
              <p>Loading equipment, topology and the 3D environment…</p>
              <div className="workspace-skeleton" />
            </>
          ) : (
            <>
              <p role="alert">{loadError}</p>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setInitAttempt((value) => value + 1)}
              >
                Retry loading lab
              </button>
            </>
          )}
        </main>
        <LabStatusBar onReplay={onReplay} />
      </div>
    );
  }

  return (
    <div className="lab-app-container">
      <LabToolbar />

      <main
        ref={workspaceRef}
        id="lab-workspace"
        className={`lab-workspace docked-workspace mode-${mode.toLowerCase()} ${
          isResizing ? "resizing" : ""
        } ${isLeftCollapsed ? "left-collapsed" : ""} ${
          isRightCollapsed ? "right-collapsed" : ""
        }`}
        style={
          {
            "--left-panel-width": isLeftCollapsed ? "0px" : `${leftWidth}px`,
            "--right-panel-width": isRightCollapsed ? "0px" : `${rightWidth}px`,
          } as React.CSSProperties
        }
        role="tabpanel"
        aria-labelledby={`mode-${mode.toLowerCase()}`}
      >
        {/* Left Sidebar */}
        <div
          className={`workspace-sidebar ${isLeftCollapsed ? "collapsed" : ""}`}
          aria-hidden={isLeftCollapsed}
        >
          {mode === "BUILD" ? (
            <BuilderPanel
              onAddAsset={(assetType) => {
                const currentAssets = historyState.present?.assets ?? [];
                const pos = getNextAssetPosition(currentAssets);
                dispatchHistory({
                  type: "ADD_ASSET",
                  payload: { assetType, position_m: pos },
                });
              }}
              onArrangeAssets={() => {
                dispatchHistory({ type: "ARRANGE_ASSETS" });
              }}
              onUndo={() => dispatchHistory({ type: "UNDO" })}
              onRedo={() => dispatchHistory({ type: "REDO" })}
              canUndo={historyState.past.length > 0}
              canRedo={historyState.future.length > 0}
            />
          ) : (
            <EquipmentCatalog />
          )}
        </div>

        {/* Left Resizer */}
        <div
          role="separator"
          tabIndex={0}
          aria-orientation="vertical"
          aria-valuenow={isLeftCollapsed ? 0 : leftWidth}
          aria-valuemin={180}
          aria-valuemax={480}
          aria-label="Resize left equipment catalog sidebar"
          className={`workspace-resizer resizer-left ${isLeftCollapsed ? "collapsed" : ""}`}
          onPointerDown={startLeftResize}
          onKeyDown={handleLeftKeyDown}
          onDoubleClick={toggleLeftCollapse}
          title={
            isLeftCollapsed
              ? "Click or drag to expand left sidebar"
              : "Drag to resize sidebar (double-click to collapse)"
          }
        >
          <div className="resizer-handle">
            <span className="resizer-grip" />
          </div>
          <button
            type="button"
            className="resizer-toggle-btn"
            aria-label={
              isLeftCollapsed ? "Expand left sidebar" : "Collapse left sidebar"
            }
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              toggleLeftCollapse();
            }}
            title={isLeftCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isLeftCollapsed ? "▶" : "◀"}
          </button>
        </div>

        {/* Center 3D & Digital Twin Stage */}
        <section
          className="workspace-stage"
          aria-label="Digital twin workspace"
        >
          {/* Edge Dock Tab for Left Sidebar when collapsed */}
          {isLeftCollapsed && (
            <button
              type="button"
              className="workspace-dock-tab dock-tab-left"
              aria-label="Expand equipment catalog"
              title="Expand equipment catalog (click to expand)"
              onClick={expandLeft}
            >
              <span className="dock-tab-arrow">▶</span>
              <span className="dock-tab-label">Catalog</span>
            </button>
          )}

          <LabViewport />
          <div className="workspace-run-controls">
            <RunControls />
            <Timeline />
          </div>
          {isFirstUse && !runId && (
            <div className="workspace-welcome">
              <div>
                <strong>Your reference lab is ready</strong>
                <p>Explore the equipment, then start a simulation.</p>
              </div>
              <div>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={handleRunReference}
                >
                  Run Reference Lab
                </button>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  disabled={creatingBlank}
                  onClick={handleStartBlank}
                >
                  {creatingBlank ? "Creating…" : "Start Blank Lab"}
                </button>
              </div>
            </div>
          )}
          {loadError && (
            <p className="workspace-inline-error" role="alert">
              {loadError}
            </p>
          )}

          {/* Edge Dock Tab for Right System Overview when collapsed */}
          {isRightCollapsed && (
            <button
              type="button"
              className="workspace-dock-tab dock-tab-right"
              aria-label="Expand system overview"
              title="Expand system overview (click to expand)"
              onClick={expandRight}
            >
              <span className="dock-tab-arrow">◀</span>
              <span className="dock-tab-label">System Overview</span>
            </button>
          )}
        </section>

        {/* Right Resizer */}
        <div
          role="separator"
          tabIndex={0}
          aria-orientation="vertical"
          aria-valuenow={isRightCollapsed ? 0 : rightWidth}
          aria-valuemin={360}
          aria-valuemax={880}
          aria-label="Resize right system overview panel"
          className={`workspace-resizer resizer-right ${isRightCollapsed ? "collapsed" : ""}`}
          onPointerDown={startRightResize}
          onKeyDown={handleRightKeyDown}
          onDoubleClick={toggleRightCollapse}
          title={
            isRightCollapsed
              ? "Click or drag to expand right panel"
              : "Drag to resize panel (double-click to collapse)"
          }
        >
          <button
            type="button"
            className="resizer-toggle-btn"
            aria-label={
              isRightCollapsed ? "Expand right panel" : "Collapse right panel"
            }
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              toggleRightCollapse();
            }}
            title={
              isRightCollapsed
                ? "Expand overview panel"
                : "Collapse overview panel"
            }
          >
            {isRightCollapsed ? "◀" : "▶"}
          </button>
          <div className="resizer-handle">
            <span className="resizer-grip" />
          </div>
        </div>

        {/* Right Monitor Sidebar */}
        <aside
          className={`workspace-monitor ${isRightCollapsed ? "collapsed" : ""}`}
          aria-hidden={isRightCollapsed}
          aria-label={
            mode === "INVESTIGATE" ? "Investigation tools" : "System monitoring"
          }
        >
          <div hidden={mode === "INVESTIGATE"}>
            <SystemOverview />
          </div>
          {mode !== "INVESTIGATE" && (
            <>
              <details className="workspace-inspector">
                <summary>
                  <LabIcon name="inspect" size={16} />
                  Equipment Inspector<span>Properties & controls</span>
                </summary>
                <Inspector />
              </details>
            </>
          )}
          {mode === "INVESTIGATE" && (
            <>
              <div className="investigate-nav-tabs">
                <button
                  type="button"
                  className={`btn btn-sm ${investigateTab === "EXPERIMENT" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setInvestigateTab("EXPERIMENT")}
                >
                  ⚡ Fault Injection
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${investigateTab === "COMPARE" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setInvestigateTab("COMPARE")}
                >
                  📊 Run Comparison
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${investigateTab === "BASELINE" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setInvestigateTab("BASELINE")}
                >
                  🧠 ML Baseline
                </button>
              </div>
              {investigateTab === "EXPERIMENT" && <ExperimentPanel />}
              {investigateTab === "COMPARE" && <RunComparison />}
              {investigateTab === "BASELINE" && <BaselinePanel />}
            </>
          )}
          {mode === "INVESTIGATE" && <IncidentInspector />}
        </aside>
      </main>
      <LabStatusBar onReplay={onReplay} />
    </div>
  );
}

export default LabApp;
