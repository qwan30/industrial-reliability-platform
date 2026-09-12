/**
 * Accessible Object Tree for equipment, pipes, and sensors with keyboard navigation.
 */

import { useState } from "react";
import { useEditorSlice, useSelectionSlice, labStore } from "./store";

export function ObjectTree() {
  const { lab } = useEditorSlice();
  const { selectedId } = useSelectionSlice();
  const [isOpen, setIsOpen] = useState(true);

  if (!lab) return null;

  return (
    <div className={`lab-panel lab-tree-panel ${isOpen ? "open" : "collapsed"}`}>
      <div className="panel-header">
        <span className="panel-title">Equipment Hierarchy</span>
        <button
          type="button"
          className="btn-icon"
          onClick={() => setIsOpen(!isOpen)}
          aria-label={isOpen ? "Collapse tree" : "Expand tree"}
        >
          {isOpen ? "◀" : "▶"}
        </button>
      </div>

      {isOpen && (
        <div className="tree-content" role="tree" aria-label="Lab Equipment">
          {/* Assets Group */}
          <div className="tree-section">
            <div className="section-title">Equipment ({lab.assets.length})</div>
            <ul className="tree-list" role="group">
              {lab.assets.map((asset) => {
                const isSelected = selectedId === asset.asset_id;
                return (
                  <li
                    key={asset.asset_id}
                    role="treeitem"
                    tabIndex={0}
                    aria-selected={isSelected}
                    className={`tree-item ${isSelected ? "selected" : ""}`}
                    onClick={() => {
                      labStore.selectEntity(asset.asset_id, "ASSET");
                      labStore.focusOn(asset.position_m);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        labStore.selectEntity(asset.asset_id, "ASSET");
                        labStore.focusOn(asset.position_m);
                      }
                    }}
                  >
                    <span className="item-badge badge-asset">{asset.type.slice(0, 4)}</span>
                    <span className="item-label">
                      {asset.type.toLowerCase().replace("_", " ")} ({asset.asset_id.slice(0, 6)})
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Pipes Group */}
          <div className="tree-section">
            <div className="section-title">Pipes ({lab.pipes.length})</div>
            <ul className="tree-list" role="group">
              {lab.pipes.map((pipe) => {
                const isSelected = selectedId === pipe.pipe_id;
                return (
                  <li
                    key={pipe.pipe_id}
                    role="treeitem"
                    tabIndex={0}
                    aria-selected={isSelected}
                    className={`tree-item ${isSelected ? "selected" : ""}`}
                    onClick={() => labStore.selectEntity(pipe.pipe_id, "PIPE")}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        labStore.selectEntity(pipe.pipe_id, "PIPE");
                      }
                    }}
                  >
                    <span className="item-badge badge-pipe">PIPE</span>
                    <span className="item-label">
                      Pipe {pipe.pipe_id.slice(0, 6)} ({pipe.from_port.port} → {pipe.to_port.port})
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Sensors Group */}
          <div className="tree-section">
            <div className="section-title">Sensors ({lab.sensors.length})</div>
            <ul className="tree-list" role="group">
              {lab.sensors.map((sensor) => {
                const isSelected = selectedId === sensor.sensor_id;
                return (
                  <li
                    key={sensor.sensor_id}
                    role="treeitem"
                    tabIndex={0}
                    aria-selected={isSelected}
                    className={`tree-item ${isSelected ? "selected" : ""}`}
                    onClick={() => labStore.selectEntity(sensor.sensor_id, "SENSOR")}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        labStore.selectEntity(sensor.sensor_id, "SENSOR");
                      }
                    }}
                  >
                    <span className={`item-badge badge-${sensor.kind.toLowerCase()}`}>
                      {sensor.kind === "PRESSURE" ? "PRES" : "FLOW"}
                    </span>
                    <span className="item-label">
                      {sensor.kind.toLowerCase()} ({sensor.sensor_id.slice(0, 6)})
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
