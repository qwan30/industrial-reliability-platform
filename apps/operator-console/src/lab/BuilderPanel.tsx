/**
 * Authoring palette for placing equipment, connecting ports, undo/redo, and saving revisions.
 */

import { useState, useEffect } from "react";
import type { AssetType, LabValidationError } from "./types";
import { useEditorSlice, labStore } from "./store";
import { updateLab, validateLabRevision } from "./api";

interface BuilderPanelProps {
  onAddAsset: (type: AssetType) => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

const CATALOG_ITEMS: Array<{ type: AssetType; label: string; icon: string; desc: string }> = [
  { type: "COMPRESSOR", label: "Compressor", icon: "⚡", desc: "Rotary air source (9.0 bar max)" },
  { type: "TANK", label: "Air Receiver Tank", icon: "🛢", desc: "0.5 m³ pressure storage buffer" },
  { type: "ISOLATION_VALVE", label: "Isolation Valve", icon: "⨂", desc: "Quarter-turn 2-position block valve" },
  { type: "CONTROL_VALVE", label: "Control Valve", icon: "⋈", desc: "Pneumatic modulating throttle valve" },
  { type: "DEMAND", label: "Pneumatic Load", icon: "⚙", desc: "Factory consumption branch" },
];

export function BuilderPanel({
  onAddAsset,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
}: BuilderPanelProps) {
  const { lab, mode } = useEditorSlice();
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<LabValidationError[]>([]);

  // Hotkeys: Ctrl+Z for Undo, Ctrl+Shift+Z or Ctrl+Y for Redo
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = document.activeElement?.tagName.toLowerCase();
      if (activeTag === "input" || activeTag === "textarea") return;

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          if (canRedo) onRedo();
        } else {
          if (canUndo) onUndo();
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        if (canRedo) onRedo();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [canUndo, canRedo, onUndo, onRedo]);

  if (mode !== "BUILD" || !lab) return null;

  const handleSaveRevision = async () => {
    setSaving(true);
    setStatusMessage(null);
    try {
      const updated = await updateLab(lab.lab_id, lab, lab.revision);
      labStore.setLab(updated);
      setStatusMessage(`Saved revision ${updated.revision} successfully`);
      setValidationErrors([]);
    } catch (err: unknown) {
      const error = err as { code?: string; message?: string };
      setStatusMessage(`Save failed: ${error.message || "Conflict"}`);
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    setValidating(true);
    setStatusMessage(null);
    try {
      const res = await validateLabRevision(lab.lab_id, lab.revision);
      if (res.run_eligible) {
        setStatusMessage("Lab is structurally sound and run-eligible");
        setValidationErrors([]);
      } else {
        setStatusMessage(`Validation failed with ${res.errors.length} error(s)`);
        setValidationErrors(res.errors);
      }
    } catch (err: unknown) {
      const error = err as { message?: string };
      setStatusMessage(`Validation request failed: ${error.message}`);
    } finally {
      setValidating(false);
    }
  };

  return (
    <div className="lab-panel lab-builder-panel">
      <div className="panel-header">
        <span className="panel-title">Equipment Catalog</span>
        <div className="undo-redo-cluster">
          <button
            type="button"
            className="btn-icon"
            onClick={onUndo}
            disabled={!canUndo}
            title="Undo (Ctrl+Z)"
            aria-label="Undo"
          >
            ↺
          </button>
          <button
            type="button"
            className="btn-icon"
            onClick={onRedo}
            disabled={!canRedo}
            title="Redo (Ctrl+Y)"
            aria-label="Redo"
          >
            ↻
          </button>
        </div>
      </div>

      <div className="builder-content">
        <div className="catalog-list">
          {CATALOG_ITEMS.map((item) => (
            <div
              key={item.type}
              className="catalog-card"
              onClick={() => onAddAsset(item.type)}
            >
              <div className="card-top">
                <span className="card-icon">{item.icon}</span>
                <span className="card-title">{item.label}</span>
              </div>
              <p className="card-desc">{item.desc}</p>
              <button
                type="button"
                className="btn btn-sm btn-secondary place-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onAddAsset(item.type);
                }}
              >
                + Place in Scene
              </button>
            </div>
          ))}
        </div>

        <div className="builder-footer-actions">
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={handleSaveRevision}
            disabled={saving}
          >
            {saving ? "Saving..." : `Commit Revision (r${lab.revision + 1})`}
          </button>

          <button
            type="button"
            className="btn btn-secondary btn-block"
            onClick={handleValidate}
            disabled={validating}
          >
            {validating ? "Validating..." : "Validate Topology"}
          </button>

          {statusMessage && <div className="builder-status-text">{statusMessage}</div>}

          {validationErrors.length > 0 && (
            <div className="validation-error-list">
              <div className="error-list-title">Issues Found:</div>
              {validationErrors.map((err, i) => (
                <div key={i} className="validation-error-item">
                  <span className="error-code">{err.code}:</span> {err.message}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
