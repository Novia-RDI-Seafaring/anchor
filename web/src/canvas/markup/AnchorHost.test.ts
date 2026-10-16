import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { NodeLike } from "../preview";
import type { ThreadItem } from "../../intent-overlay";
import { useAnchorOverlayHost } from "./AnchorHost";

const geometry = {
  storeNodes: {} as Record<string, NodeLike>, storeEdges: {},
  viewport: { x: 0, y: 0, zoom: 1 },
  getViewport: vi.fn(), setViewport: vi.fn(), toFlow: vi.fn(), rowsOf: vi.fn(), edgesOf: vi.fn(),
};
vi.mock("./AnchorGeometry", () => ({ useAnchorGeometry: () => geometry }));

describe("Anchor suggestion preview feedback", () => {
  it("passes live missing-target feedback to the independent overlay without changing the operation", () => {
    geometry.storeNodes = { card: { id: "card", x: 10, y: 20, label: "Before" } };
    const suggestion: ThreadItem = {
      id: "suggestion", type: "suggestion", author: { kind: "agent" }, created_at: 1,
      text: "Rename the card", state: "pending",
      ops: [{ type: "NodeUpdated", payload: { id: "card", fields: { label: "After" } } }],
    };
    const original = structuredClone(suggestion);
    const { result, rerender } = renderHook(() => useAnchorOverlayHost("canvas", []));
    expect(result.current.display.preview(suggestion)).toMatchObject({
      stale: false, nodes: [{ id: "card", kind: "updated", label: "After" }],
    });
    geometry.storeNodes = { card: { id: "card", x: 30, y: 40, label: "Still here" } };
    rerender();
    expect(result.current.display.preview(suggestion)?.stale).toBe(false);
    geometry.storeNodes = {};
    rerender();
    expect(result.current.display.preview(suggestion)).toEqual({ stale: true, nodes: [], edges: [] });
    expect(suggestion).toEqual(original);
  });
});
