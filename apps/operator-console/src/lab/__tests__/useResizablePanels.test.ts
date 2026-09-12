import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { useResizablePanels } from "../useResizablePanels";

describe("useResizablePanels", () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement("div");
    // Mock getBoundingClientRect
    container.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      right: 1200,
      bottom: 800,
      width: 1200,
      height: 800,
      x: 0,
      y: 0,
      toJSON: () => {},
    });
    document.body.appendChild(container);
  });

  afterEach(() => {
    container.remove();
  });

  it("initializes with default widths and uncollapsed state", () => {
    const { result } = renderHook(() =>
      useResizablePanels({
        initialLeftWidth: 260,
        initialRightWidth: 560,
        containerRef: { current: container },
      }),
    );

    expect(result.current.leftWidth).toBe(260);
    expect(result.current.rightWidth).toBe(560);
    expect(result.current.isLeftCollapsed).toBe(false);
    expect(result.current.isRightCollapsed).toBe(false);
  });

  it("clamps manual widths within min and max boundaries", () => {
    const { result } = renderHook(() =>
      useResizablePanels({
        minLeftWidth: 180,
        maxLeftWidth: 480,
        minRightWidth: 360,
        maxRightWidth: 850,
        containerRef: { current: container },
      }),
    );

    act(() => {
      result.current.setLeftWidth(100);
    });
    expect(result.current.leftWidth).toBe(180);

    act(() => {
      result.current.setLeftWidth(600);
    });
    expect(result.current.leftWidth).toBe(480);

    act(() => {
      result.current.setRightWidth(200);
    });
    expect(result.current.rightWidth).toBe(360);

    act(() => {
      result.current.setRightWidth(1000);
    });
    expect(result.current.rightWidth).toBe(850);
  });

  it("toggles collapse state and restores previous width when expanded", () => {
    const { result } = renderHook(() =>
      useResizablePanels({
        initialLeftWidth: 280,
        initialRightWidth: 540,
        containerRef: { current: container },
      }),
    );

    act(() => {
      result.current.toggleLeftCollapse();
    });
    expect(result.current.isLeftCollapsed).toBe(true);

    act(() => {
      result.current.toggleLeftCollapse();
    });
    expect(result.current.isLeftCollapsed).toBe(false);
    expect(result.current.leftWidth).toBe(280);

    act(() => {
      result.current.toggleRightCollapse();
    });
    expect(result.current.isRightCollapsed).toBe(true);

    act(() => {
      result.current.expandRight();
    });
    expect(result.current.isRightCollapsed).toBe(false);
    expect(result.current.rightWidth).toBe(540);
  });

  it("supports keyboard resizing and collapse toggle for accessibility", () => {
    const { result } = renderHook(() =>
      useResizablePanels({
        initialLeftWidth: 260,
        initialRightWidth: 500,
        minLeftWidth: 180,
        containerRef: { current: container },
      }),
    );

    // Left resizer: ArrowLeft shrinks
    act(() => {
      result.current.handleLeftKeyDown({
        key: "ArrowLeft",
        preventDefault: () => {},
      } as any);
    });
    expect(result.current.leftWidth).toBe(240);

    // Left resizer: ArrowRight grows
    act(() => {
      result.current.handleLeftKeyDown({
        key: "ArrowRight",
        preventDefault: () => {},
      } as any);
    });
    expect(result.current.leftWidth).toBe(260);

    // Enter toggles collapse
    act(() => {
      result.current.handleLeftKeyDown({
        key: "Enter",
        preventDefault: () => {},
      } as any);
    });
    expect(result.current.isLeftCollapsed).toBe(true);

    // Right resizer: ArrowLeft increases width (expands panel leftward)
    act(() => {
      result.current.handleRightKeyDown({
        key: "ArrowLeft",
        preventDefault: () => {},
      } as any);
    });
    expect(result.current.rightWidth).toBe(520);

    // Right resizer: ArrowRight decreases width
    act(() => {
      result.current.handleRightKeyDown({
        key: "ArrowRight",
        preventDefault: () => {},
      } as any);
    });
    expect(result.current.rightWidth).toBe(500);

    // Space toggles right collapse
    act(() => {
      result.current.handleRightKeyDown({
        key: " ",
        preventDefault: () => {},
      } as any);
    });
    expect(result.current.isRightCollapsed).toBe(true);
  });

  it("persists width and collapsed states to localStorage", () => {
    const { result } = renderHook(() =>
      useResizablePanels({
        storagePrefix: "test-irp",
        initialLeftWidth: 260,
        containerRef: { current: container },
      }),
    );

    act(() => {
      result.current.setLeftWidth(320);
      result.current.toggleRightCollapse();
    });

    expect(localStorage.getItem("test-irp.leftWidth")).toBe("320");
    expect(localStorage.getItem("test-irp.isRightCollapsed")).toBe("true");

    // Second instance loads persisted values
    const { result: instance2 } = renderHook(() =>
      useResizablePanels({
        storagePrefix: "test-irp",
        containerRef: { current: container },
      }),
    );

    expect(instance2.current.leftWidth).toBe(320);
    expect(instance2.current.isRightCollapsed).toBe(true);
  });
});
