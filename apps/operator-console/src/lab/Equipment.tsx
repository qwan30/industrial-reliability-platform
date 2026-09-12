/**
 * 3D Equipment representation with GLB mesh rendering, selection, port anchors, and animation.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { Asset, PortName } from "./types";
import { GLB_FILES, LOCAL_ANCHORS, ASSET_BOUNDS } from "./sceneBindings";
import { useSelectionSlice, useRunSlice, labStore } from "./store";

// Preload all 5 equipment GLB models
Object.values(GLB_FILES).forEach((url) => useGLTF.preload(url));

interface EquipmentProps {
  asset: Asset;
}

export function Equipment({ asset }: EquipmentProps) {
  const { selectedId, selectedPort } = useSelectionSlice();
  const { snapshot } = useRunSlice();
  const isSelected = selectedId === asset.asset_id;

  const glbUrl = GLB_FILES[asset.type];
  const { scene } = useGLTF(glbUrl);

  // Clone scene instance for this asset
  const clonedScene = useMemo(() => scene.clone(true), [scene]);

  const groupRef = useRef<THREE.Group>(null);
  const rotorRef = useRef<THREE.Object3D | null>(null);
  const handleRef = useRef<THREE.Object3D | null>(null);

  // Find animated child nodes in cloned scene
  useMemo(() => {
    clonedScene.traverse((child) => {
      if (child.name === "rotor") {
        rotorRef.current = child;
      } else if (child.name === "handle") {
        handleRef.current = child;
      }
    });
  }, [clonedScene]);

  // Animation frame loop
  useFrame((_, delta) => {
    // Spin compressor rotor if running
    if (asset.type === "COMPRESSOR" && rotorRef.current) {
      const mode = snapshot?.physical.operating_modes[asset.asset_id];
      const isRunning = mode ? mode === "RUNNING" : Boolean(asset.parameters.enabled);
      if (isRunning) {
        rotorRef.current.rotation.z += delta * 12.0; // Simulated rotation speed
      }
    }

    // Adjust isolation valve handle (0 open, PI/2 closed)
    if (asset.type === "ISOLATION_VALVE" && handleRef.current) {
      const opening = typeof asset.parameters.opening === "number" ? asset.parameters.opening : 1.0;
      const targetAngle = opening >= 0.5 ? 0.0 : Math.PI / 2;
      handleRef.current.rotation.y = THREE.MathUtils.lerp(handleRef.current.rotation.y, targetAngle, 0.15);
    }
  });

  const bounds = ASSET_BOUNDS[asset.type] || [0.5, 0.5, 0.5];
  const anchors = LOCAL_ANCHORS[asset.type] || {};

  return (
    <group
      ref={groupRef}
      position={asset.position_m}
      rotation={[0, asset.rotation_y_rad, 0]}
      onClick={(e) => {
        e.stopPropagation();
        labStore.selectEntity(asset.asset_id, "ASSET");
        labStore.focusOn(asset.position_m);
      }}
    >
      <primitive object={clonedScene} />

      {/* Selection Bounding Wireframe */}
      {isSelected && (
        <mesh position={[0, bounds[1], 0]}>
          <boxGeometry args={[bounds[0] * 2 + 0.1, bounds[1] * 2 + 0.1, bounds[2] * 2 + 0.1]} />
          <meshBasicMaterial color={0x00a8ff} wireframe transparent opacity={0.6} />
        </mesh>
      )}

      {/* Port Anchors */}
      {Object.entries(anchors).map(([portKey, localPos]) => {
        const portName = portKey as PortName;
        const isPortSelected = isSelected && selectedPort === portName;
        return (
          <mesh
            key={portKey}
            position={localPos}
            onClick={(e) => {
              e.stopPropagation();
              labStore.selectEntity(asset.asset_id, "ASSET", portName);
            }}
          >
            <sphereGeometry args={[isPortSelected ? 0.07 : 0.045, 16, 16]} />
            <meshStandardMaterial
              color={isPortSelected ? 0x00ff88 : 0x00a8ff}
              emissive={isPortSelected ? 0x00aa55 : 0x004488}
              emissiveIntensity={0.6}
            />
          </mesh>
        );
      })}
    </group>
  );
}
