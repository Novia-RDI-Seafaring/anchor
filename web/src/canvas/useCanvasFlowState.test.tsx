import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";
import { useCanvasStore, type CanvasNode } from "@/stores/canvasStore";

import { useCanvasFlowState } from "./useCanvasFlowState";

vi.mock("@/api/canvases", () => ({
  canvases: {
    removeNode: vi.fn(async () => undefined),
    removeEdge: vi.fn(async () => undefined),
    patchNode: vi.fn(async () => undefined),
    addEdge: vi.fn(async () => undefined),
  },
}));

function node(id: string, fields: Partial<CanvasNode> = {}): CanvasNode {
  return {
    id,
    node_type: "concept",
    label: id,
    x: 10,
    y: 20,
    data: {},
    ...fields,
  };
}

describe("useCanvasFlowState", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCanvasStore.setState({
      slug: "demo",
      version: 1,
      nodes: {},
      edges: {},
      activity: [],
    });
  });

  it("projects store nodes and persists an optimistic remove", async () => {
    useCanvasStore.setState({ nodes: { one: node("one") } });
    const { result } = renderHook(() => useCanvasFlowState("demo", false));
    await waitFor(() => expect(result.current.rfNodes).toHaveLength(1));

    act(() => {
      result.current.onNodesChange([{ type: "remove", id: "one" }]);
    });

    expect(useCanvasStore.getState().nodes).toEqual({});
    await waitFor(() => expect(canvases.removeNode).toHaveBeenCalledWith("demo", "one"));
  });

  it("materializes row-to-region provenance through one connect gesture", async () => {
    useCanvasStore.setState({
      nodes: {
        spec: node("spec", {
          node_type: "spec",
          data: {
            rows: [{ key: "pressure", source_ref: { page: 4, bbox: [1, 2, 3, 4] } }],
          },
        }),
        document: node("document", {
          node_type: "document",
          data: { slug: "pump-datasheet" },
        }),
      },
    });
    const { result } = renderHook(() => useCanvasFlowState("demo", false));

    act(() => {
      result.current.onConnect({
        source: "spec",
        target: "document",
        sourceHandle: "row:0:pressure",
        targetHandle: "region:region-7",
      });
    });

    await waitFor(() => {
      expect(canvases.addEdge).toHaveBeenCalledWith("demo", expect.objectContaining({
        source: "spec",
        target: "document",
        edge_type: "anchored",
        data: expect.objectContaining({
          source_doc_slug: "pump-datasheet",
          source_region_id: "region-7",
        }),
      }));
      expect(canvases.patchNode).toHaveBeenCalledWith("demo", "spec", {
        data: expect.objectContaining({
          rows: [expect.objectContaining({
            source_ref: {
              page: 4,
              region_id: "region-7",
              bbox: [1, 2, 3, 4],
            },
          })],
        }),
      });
    });
  });
});
