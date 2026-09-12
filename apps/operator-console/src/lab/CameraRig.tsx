/**
 * Camera controller supporting Orbit and First-Person Walk-through modes.
 */

import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { useCameraSlice } from "./store";

const HOME_POSITION = new THREE.Vector3(24, 22, 28);
const HOME_TARGET = new THREE.Vector3(0, 1, 0);
const EYE_HEIGHT = 1.65;

export function CameraRig() {
  const { mode, focusTarget, focusCounter } = useCameraSlice();
  const { camera, gl, size } = useThree();
  const controlsRef = useRef<OrbitControlsImpl>(null);

  // Preserve horizontal coverage on portrait screens without overriding user orbit/zoom.
  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera)) return;
    const aspect = size.width / Math.max(size.height, 1);
    camera.fov = THREE.MathUtils.radToDeg(
      2 *
        Math.atan(
          Math.tan(THREE.MathUtils.degToRad(45) / 2) / Math.min(aspect, 1),
        ),
    );
    camera.updateProjectionMatrix();
  }, [camera, size.width, size.height]);

  // Keyboard navigation state for Walk mode
  const keysDown = useRef<Record<string, boolean>>({});

  // Setup keyboard handlers
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept shortcuts if typing in text input
      const activeTag = document.activeElement?.tagName.toLowerCase();
      if (
        activeTag === "input" ||
        activeTag === "textarea" ||
        activeTag === "select"
      ) {
        return;
      }

      keysDown.current[e.code] = true;

      if (e.code === "KeyH") {
        controlsRef.current?.target.copy(HOME_TARGET);
        camera.position.copy(HOME_POSITION);
        controlsRef.current?.update();
      } else if (e.code === "KeyF" && focusTarget) {
        controlsRef.current?.target.set(
          focusTarget[0],
          focusTarget[1],
          focusTarget[2],
        );
        camera.position.set(
          focusTarget[0] + 3,
          focusTarget[1] + 2,
          focusTarget[2] + 4,
        );
        controlsRef.current?.update();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      keysDown.current[e.code] = false;
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [camera, focusTarget]);

  // React to programmatic focus triggers
  useEffect(() => {
    if (focusTarget && controlsRef.current) {
      controlsRef.current.target.set(
        focusTarget[0],
        focusTarget[1],
        focusTarget[2],
      );
      camera.position.set(
        focusTarget[0] + 3.5,
        focusTarget[1] + 2.5,
        focusTarget[2] + 4.5,
      );
      controlsRef.current.update();
    }
  }, [focusCounter, focusTarget, camera]);

  // Frame update for Walk mode WASD movement
  useFrame((_, delta) => {
    if (mode !== "WALK") return;

    const speed =
      keysDown.current["ShiftLeft"] || keysDown.current["ShiftRight"]
        ? 6.0
        : 4.0;
    const moveDist = speed * delta;

    const forward = new THREE.Vector3();
    camera.getWorldDirection(forward);
    forward.y = 0;
    forward.normalize();

    const right = new THREE.Vector3();
    right.crossVectors(camera.up, forward).negate().normalize();

    const moveVector = new THREE.Vector3();

    if (keysDown.current["KeyW"] || keysDown.current["ArrowUp"])
      moveVector.add(forward);
    if (keysDown.current["KeyS"] || keysDown.current["ArrowDown"])
      moveVector.sub(forward);
    if (keysDown.current["KeyD"] || keysDown.current["ArrowRight"])
      moveVector.add(right);
    if (keysDown.current["KeyA"] || keysDown.current["ArrowLeft"])
      moveVector.sub(right);

    if (moveVector.lengthSq() > 0) {
      moveVector.normalize().multiplyScalar(moveDist);
      camera.position.add(moveVector);

      // Clamp inside factory room bounds
      camera.position.x = Math.max(-11.5, Math.min(11.5, camera.position.x));
      camera.position.z = Math.max(-7.5, Math.min(7.5, camera.position.z));
      camera.position.y = EYE_HEIGHT;

      if (controlsRef.current) {
        controlsRef.current.target.add(moveVector);
      }
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      args={[camera, gl.domElement]}
      makeDefault
      enabled={true}
      enableDamping={true}
      dampingFactor={0.08}
      minDistance={1.0}
      maxDistance={40.0}
      maxPolarAngle={Math.PI / 2 - 0.02} // Do not dip below ground plane
    />
  );
}
