/**
 * 3D Port connector tool for drawing pipes between equipment ports.
 */

import { useState, useEffect } from "react";
import type { Asset, PortRef } from "./types";
import { computePortWorldPosition } from "./sceneBindings";
import { useSelectionSlice, labStore } from "./store";

interface PortConnectorProps {
  assetMap: Map<string, Asset>;
  onConnectPorts: (from: PortRef, to: PortRef) => void;
}

export function PortConnector({ assetMap, onConnectPorts }: PortConnectorProps) {
  const { selectedId, selectedPort } = useSelectionSlice();
  const [sourcePort, setSourcePort] = useState<PortRef | null>(null);

  // When a port is clicked, either start or complete connection
  useEffect(() => {
    if (!selectedId || !selectedPort) return;

    if (!sourcePort) {
      // First port selected: start connection
      setSourcePort({ asset_id: selectedId, port: selectedPort });
    } else {
      // Second port clicked: complete pipe if different
      if (sourcePort.asset_id !== selectedId || sourcePort.port !== selectedPort) {
        onConnectPorts(sourcePort, { asset_id: selectedId, port: selectedPort });
        setSourcePort(null);
        labStore.clearSelection();
      }
    }
  }, [selectedId, selectedPort, sourcePort, onConnectPorts]);

  // Cancel with Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSourcePort(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  if (!sourcePort) return null;

  const sourceAsset = assetMap.get(sourcePort.asset_id);
  if (!sourceAsset) return null;

  const startPos = computePortWorldPosition(
    sourceAsset.type,
    sourceAsset.position_m,
    sourceAsset.rotation_y_rad,
    sourcePort.port
  );

  return (
    <group name="PORT_CONNECT_PREVIEW">
      {/* Visual glowing beacon on active source port */}
      <mesh position={startPos}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshStandardMaterial
          color={0x00ff88}
          emissive={0x00aa55}
          emissiveIntensity={1.0}
        />
      </mesh>
    </group>
  );
}
