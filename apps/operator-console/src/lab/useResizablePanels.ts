import { useState, useEffect, useRef, useCallback } from "react";

export interface ResizablePanelsOptions {
  initialLeftWidth?: number;
  minLeftWidth?: number;
  maxLeftWidth?: number;
  collapseLeftThreshold?: number;

  initialRightWidth?: number;
  minRightWidth?: number;
  maxRightWidth?: number;
  collapseRightThreshold?: number;

  storagePrefix?: string;
  containerRef?: React.RefObject<HTMLElement | null>;
}

export interface ResizablePanelsState {
  leftWidth: number;
  rightWidth: number;
  isLeftCollapsed: boolean;
  isRightCollapsed: boolean;
  isResizing: boolean;
  resizingSide: "left" | "right" | null;

  startLeftResize: (e: React.PointerEvent) => void;
  startRightResize: (e: React.PointerEvent) => void;

  toggleLeftCollapse: () => void;
  toggleRightCollapse: () => void;

  expandLeft: () => void;
  expandRight: () => void;

  setLeftWidth: (w: number) => void;
  setRightWidth: (w: number) => void;

  handleLeftKeyDown: (e: React.KeyboardEvent) => void;
  handleRightKeyDown: (e: React.KeyboardEvent) => void;
}

export function useResizablePanels({
  initialLeftWidth = 260,
  minLeftWidth = 180,
  maxLeftWidth = 480,
  collapseLeftThreshold = 120,

  initialRightWidth = 560,
  minRightWidth = 360,
  maxRightWidth = 850,
  collapseRightThreshold = 200,

  storagePrefix = "irp.workspace",
  containerRef,
}: ResizablePanelsOptions = {}): ResizablePanelsState {
  // Load persisted values if available
  const [leftWidth, setLeftWidthState] = useState<number>(() => {
    if (typeof localStorage !== "undefined") {
      const saved = localStorage.getItem(`${storagePrefix}.leftWidth`);
      if (saved) {
        const val = Number(saved);
        if (!isNaN(val) && val >= minLeftWidth && val <= maxLeftWidth) {
          return val;
        }
      }
    }
    return initialLeftWidth;
  });

  const [rightWidth, setRightWidthState] = useState<number>(() => {
    if (typeof localStorage !== "undefined") {
      const saved = localStorage.getItem(`${storagePrefix}.rightWidth`);
      if (saved) {
        const val = Number(saved);
        if (!isNaN(val) && val >= minRightWidth && val <= maxRightWidth) {
          return val;
        }
      }
    }
    return initialRightWidth;
  });

  const [isLeftCollapsed, setIsLeftCollapsed] = useState<boolean>(() => {
    if (typeof localStorage !== "undefined") {
      return (
        localStorage.getItem(`${storagePrefix}.isLeftCollapsed`) === "true"
      );
    }
    return false;
  });

  const [isRightCollapsed, setIsRightCollapsed] = useState<boolean>(() => {
    if (typeof localStorage !== "undefined") {
      return (
        localStorage.getItem(`${storagePrefix}.isRightCollapsed`) === "true"
      );
    }
    return false;
  });

  const [resizingSide, setResizingSide] = useState<"left" | "right" | null>(
    null,
  );

  // Store last uncollapsed widths to restore
  const lastLeftWidthRef = useRef<number>(leftWidth);
  const lastRightWidthRef = useRef<number>(rightWidth);

  // Persist state changes
  useEffect(() => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(`${storagePrefix}.leftWidth`, String(leftWidth));
      localStorage.setItem(
        `${storagePrefix}.isLeftCollapsed`,
        String(isLeftCollapsed),
      );
    }
  }, [leftWidth, isLeftCollapsed, storagePrefix]);

  useEffect(() => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(`${storagePrefix}.rightWidth`, String(rightWidth));
      localStorage.setItem(
        `${storagePrefix}.isRightCollapsed`,
        String(isRightCollapsed),
      );
    }
  }, [rightWidth, isRightCollapsed, storagePrefix]);

  const setLeftWidth = useCallback(
    (w: number) => {
      const clamped = Math.max(minLeftWidth, Math.min(maxLeftWidth, w));
      lastLeftWidthRef.current = clamped;
      setLeftWidthState(clamped);
    },
    [minLeftWidth, maxLeftWidth],
  );

  const setRightWidth = useCallback(
    (w: number) => {
      const clamped = Math.max(minRightWidth, Math.min(maxRightWidth, w));
      lastRightWidthRef.current = clamped;
      setRightWidthState(clamped);
    },
    [minRightWidth, maxRightWidth],
  );

  const toggleLeftCollapse = useCallback(() => {
    setIsLeftCollapsed((prev) => {
      const next = !prev;
      if (!next) {
        setLeftWidthState(lastLeftWidthRef.current || initialLeftWidth);
      }
      return next;
    });
  }, [initialLeftWidth]);

  const expandLeft = useCallback(() => {
    setIsLeftCollapsed(false);
    setLeftWidthState(lastLeftWidthRef.current || initialLeftWidth);
  }, [initialLeftWidth]);

  const toggleRightCollapse = useCallback(() => {
    setIsRightCollapsed((prev) => {
      const next = !prev;
      if (!next) {
        setRightWidthState(lastRightWidthRef.current || initialRightWidth);
      }
      return next;
    });
  }, [initialRightWidth]);

  const expandRight = useCallback(() => {
    setIsRightCollapsed(false);
    setRightWidthState(lastRightWidthRef.current || initialRightWidth);
  }, [initialRightWidth]);

  // Pointer drag for left resizer
  const startLeftResize = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      setResizingSide("left");

      const onPointerMove = (moveEvent: PointerEvent) => {
        let containerLeft = 0;
        if (containerRef?.current) {
          containerLeft = containerRef.current.getBoundingClientRect().left;
        }
        const currentX = moveEvent.clientX - containerLeft;

        if (currentX < collapseLeftThreshold) {
          setIsLeftCollapsed(true);
        } else {
          setIsLeftCollapsed(false);
          const clamped = Math.max(
            minLeftWidth,
            Math.min(maxLeftWidth, currentX),
          );
          lastLeftWidthRef.current = clamped;
          setLeftWidthState(clamped);
        }
      };

      const onPointerUp = () => {
        setResizingSide(null);
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("pointerup", onPointerUp);
        window.removeEventListener("pointercancel", onPointerUp);
        document.body.classList.remove("workspace-is-resizing");
      };

      document.body.classList.add("workspace-is-resizing");
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
      window.addEventListener("pointercancel", onPointerUp);
    },
    [containerRef, collapseLeftThreshold, minLeftWidth, maxLeftWidth],
  );

  // Pointer drag for right resizer
  const startRightResize = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      setResizingSide("right");

      const onPointerMove = (moveEvent: PointerEvent) => {
        let containerRight = window.innerWidth;
        if (containerRef?.current) {
          containerRight = containerRef.current.getBoundingClientRect().right;
        }
        const currentWidth = containerRight - moveEvent.clientX;

        if (currentWidth < collapseRightThreshold) {
          setIsRightCollapsed(true);
        } else {
          setIsRightCollapsed(false);
          const clamped = Math.max(
            minRightWidth,
            Math.min(maxRightWidth, currentWidth),
          );
          lastRightWidthRef.current = clamped;
          setRightWidthState(clamped);
        }
      };

      const onPointerUp = () => {
        setResizingSide(null);
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("pointerup", onPointerUp);
        window.removeEventListener("pointercancel", onPointerUp);
        document.body.classList.remove("workspace-is-resizing");
      };

      document.body.classList.add("workspace-is-resizing");
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
      window.addEventListener("pointercancel", onPointerUp);
    },
    [containerRef, collapseRightThreshold, minRightWidth, maxRightWidth],
  );

  // Keyboard accessibility: Left Resizer
  const handleLeftKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const step = 20;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (isLeftCollapsed) return;
        if (leftWidth - step < minLeftWidth) {
          toggleLeftCollapse();
        } else {
          setLeftWidth(leftWidth - step);
        }
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        if (isLeftCollapsed) {
          expandLeft();
        } else {
          setLeftWidth(leftWidth + step);
        }
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleLeftCollapse();
      }
    },
    [
      leftWidth,
      isLeftCollapsed,
      minLeftWidth,
      setLeftWidth,
      toggleLeftCollapse,
      expandLeft,
    ],
  );

  // Keyboard accessibility: Right Resizer
  const handleRightKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const step = 20;
      if (e.key === "ArrowLeft") {
        // Arrow left expands right sidebar toward the center
        e.preventDefault();
        if (isRightCollapsed) {
          expandRight();
        } else {
          setRightWidth(rightWidth + step);
        }
      } else if (e.key === "ArrowRight") {
        // Arrow right shrinks right sidebar toward edge
        e.preventDefault();
        if (isRightCollapsed) return;
        if (rightWidth - step < minRightWidth) {
          toggleRightCollapse();
        } else {
          setRightWidth(rightWidth - step);
        }
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleRightCollapse();
      }
    },
    [
      rightWidth,
      isRightCollapsed,
      minRightWidth,
      setRightWidth,
      toggleRightCollapse,
      expandRight,
    ],
  );

  return {
    leftWidth,
    rightWidth,
    isLeftCollapsed,
    isRightCollapsed,
    isResizing: resizingSide !== null,
    resizingSide,

    startLeftResize,
    startRightResize,

    toggleLeftCollapse,
    toggleRightCollapse,

    expandLeft,
    expandRight,

    setLeftWidth,
    setRightWidth,

    handleLeftKeyDown,
    handleRightKeyDown,
  };
}
