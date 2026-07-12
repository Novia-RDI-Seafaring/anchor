import { act, renderHook, waitFor } from "@testing-library/react";
import type { DragEvent } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";

import { useCanvasDrop } from "./useCanvasDrop";

vi.mock("@/api/canvases", () => ({
  canvases: {
    addNode: vi.fn(async () => ({ event: { payload: { id: "new-node" } } })),
    addEdge: vi.fn(async () => undefined),
    createSubCanvas: vi.fn(async () => undefined),
    uploadFile: vi.fn(async () => undefined),
  },
}));

describe("useCanvasDrop", () => {
  beforeEach(() => vi.clearAllMocks());

  it("turns a canvas-link payload into a canvas node", async () => {
    const { result } = renderHook(() => useCanvasDrop("home", (point) => point));
    const preventDefault = vi.fn();
    const event = {
      clientX: 120,
      clientY: 80,
      preventDefault,
      dataTransfer: {
        files: [],
        types: ["application/x-anchor-canvas-link"],
        getData: (type: string) => type === "application/x-anchor-canvas-link"
          ? JSON.stringify({ slug: "child", title: "Child canvas" })
          : "",
      },
    } as unknown as DragEvent;

    await act(async () => result.current.onDrop(event));

    expect(preventDefault).toHaveBeenCalled();
    expect(canvases.addNode).toHaveBeenCalledWith("home", {
      node_type: "canvas",
      label: "Child canvas",
      x: 120,
      y: 80,
      data: { canvas_slug: "child", title: "Child canvas" },
    });
  });

  it("creates an evidence edge for a dropped sourced node", async () => {
    const { result } = renderHook(() => useCanvasDrop("home", (point) => point));
    const payload = {
      node_type: "fact",
      label: "Pressure",
      data: {
        source_doc_node_id: "document-1",
        source_region_id: "region-2",
        source_ref: { page: 3 },
      },
    };
    const event = {
      clientX: 30,
      clientY: 40,
      preventDefault: vi.fn(),
      dataTransfer: {
        files: [],
        types: ["application/x-anchor-node"],
        getData: (type: string) => type === "application/x-anchor-node"
          ? JSON.stringify(payload)
          : "",
      },
    } as unknown as DragEvent;

    await act(async () => result.current.onDrop(event));

    await waitFor(() => expect(canvases.addEdge).toHaveBeenCalledWith("home", {
      source: "new-node",
      target: "document-1",
      edge_type: "anchored",
      data: {
        kind: "evidence",
        source_ref: { page: 3 },
        source_region_id: "region-2",
      },
    }));
  });
});
