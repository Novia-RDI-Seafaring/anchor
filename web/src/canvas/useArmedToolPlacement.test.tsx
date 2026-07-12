import { act, renderHook, waitFor } from "@testing-library/react";
import type { PointerEvent } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";
import { useUiStore } from "@/stores/uiStore";

import { useArmedToolPlacement } from "./useArmedToolPlacement";

vi.mock("@/api/canvases", () => ({
  canvases: {
    addNode: vi.fn(async () => undefined),
    createSubCanvas: vi.fn(async () => undefined),
  },
}));

function pointer(x: number, y: number): PointerEvent {
  return {
    clientX: x,
    clientY: y,
    target: document.createElement("div"),
  } as unknown as PointerEvent;
}

describe("useArmedToolPlacement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUiStore.setState({ armedTool: null });
  });

  it("places a click-armed concept and disarms", async () => {
    useUiStore.setState({ armedTool: "concept" });
    const { result } = renderHook(() => useArmedToolPlacement("demo", (point) => point));

    act(() => {
      result.current.pointerHandlers.onPointerDown(pointer(50, 60));
      result.current.pointerHandlers.onPointerUp(pointer(51, 61));
    });

    await waitFor(() => expect(canvases.addNode).toHaveBeenCalledWith(
      "demo",
      expect.objectContaining({ node_type: "concept", x: 50, y: 60 }),
    ));
    await waitFor(() => expect(useUiStore.getState().armedTool).toBeNull());
  });

  it("uses the painted rectangle as flow position and size", async () => {
    useUiStore.setState({ armedTool: "area" });
    const toFlow = (point: { x: number; y: number }) => ({
      x: point.x / 2,
      y: point.y / 2,
    });
    const { result } = renderHook(() => useArmedToolPlacement("demo", toFlow));

    act(() => {
      result.current.pointerHandlers.onPointerDown(pointer(20, 40));
      result.current.pointerHandlers.onPointerMove(pointer(220, 140));
      result.current.pointerHandlers.onPointerUp(pointer(220, 140));
    });

    await waitFor(() => expect(canvases.addNode).toHaveBeenCalledWith(
      "demo",
      expect.objectContaining({
        node_type: "area",
        x: 10,
        y: 20,
        width: 100,
        height: 50,
      }),
    ));
  });
});
