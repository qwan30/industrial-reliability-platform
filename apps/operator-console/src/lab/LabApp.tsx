/**
 * Main Virtual Lab Application container.
 */

import { useEffect, useState, useReducer } from "react";
import { LabToolbar } from "./LabToolbar";
import { LabScene } from "./LabScene";
import { ObjectTree } from "./ObjectTree";
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
import { editorReducer, initialEditorState } from "./editorReducer";
import { useRunSlice, labStore } from "./store";
import { getReferenceTemplate, createLab, getLab } from "./api";
import "./lab.css";

export function LabApp() {
  const { runId } = useRunSlice();
  const { lab, mode } = useEditorSlice();
  const [historyState, dispatchHistory] = useReducer(editorReducer, initialEditorState());

  // Sync external lab store when history state changes
  useEffect(() => {
    if (historyState.present && historyState.present !== lab) {
      labStore.setLab(historyState.present);
    }
  }, [historyState.present, lab]);

  // Sync initial lab into history state
  useEffect(() => {
    if (lab && !historyState.present) {
      dispatchHistory({ type: "SET_LAB", payload: lab });
    }
  }, [lab, historyState.present]);
  const [isFirstUse, setIsFirstUse] = useState(true);
  const [loading, setLoading] = useState(true);
  useLabStream(runId);

  useEffect(() => {
    async function initLab() {
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
          labStore.focusOn(firstComp.position_m);
        }
      } catch (err) {
        console.error("Failed to load reference lab:", err);
      } finally {
        setLoading(false);
      }
    }

    initLab();
  }, []);

  const handleRunReference = async () => {
    setIsFirstUse(false);
    labStore.setMode("OPERATE");
  };

  const handleStartBlank = async () => {
    try {
      const blank = await createLab("Blank Industrial Lab", "BLANK");
      labStore.setLab(blank);
      labStore.clearSelection();
      localStorage.setItem("irp.lastLabId", blank.lab_id);
      setIsFirstUse(false);
      labStore.setMode("BUILD");
    } catch (err) {
      console.error("Failed to start blank lab:", err);
    }
  };

  if (loading) {
    return (
      <div className="lab-app-container loading-container">
        <div className="loading-spinner">Initializing 3D Industrial Virtual Lab...</div>
      </div>
    );
  }

  return (
    <div className="lab-app-container">
      <LabToolbar />

      <main className="lab-workspace">
        {mode === "BUILD" ? (
          <BuilderPanel
            onAddAsset={(assetType) => {
              dispatchHistory({
                type: "ADD_ASSET",
                payload: { assetType, position_m: [0, 0, 0] },
              });
            }}
            onUndo={() => dispatchHistory({ type: "UNDO" })}
            onRedo={() => dispatchHistory({ type: "REDO" })}
            canUndo={historyState.past.length > 0}
            canRedo={historyState.future.length > 0}
          />
        ) : (
          <>
            <ObjectTree />
            {mode === "OPERATE" && <IncidentInspector />}
          </>
        )}
        <LabScene />
        <Inspector />
        {mode === "INVESTIGATE" && <ExperimentPanel />}
        {mode === "INVESTIGATE" && <RunComparison />}
        {mode === "INVESTIGATE" && <BaselinePanel />}
        <RunControls />
        <Timeline />

        {/* First-use banner */}
        {isFirstUse && !runId && (
          <div className="welcome-overlay">
            <div className="welcome-text">
              <h2>Welcome to the 3D Industrial Virtual Lab</h2>
              <p>Explore the 4-train pneumatic compressor system or build your own custom topology.</p>
            </div>
            <div className="welcome-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleRunReference}
              >
                Run Reference Lab
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleStartBlank}
              >
                Start Blank Lab
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
export default LabApp;
