import { afterEach, describe, expect, it } from "vitest";
import { changesOf, markChanges } from "./changeMarks";

const nodes = {
  kept: { id: "kept", x: 0, y: 0, width: 100, height: 50, data: { label: "Hippity hopp" } },
  fresh: { id: "fresh", x: 200, y: 0, width: 100, height: 50, data: { label: "Techno" } },
};
const edges = { e1: { id: "e1", source: "kept", target: "fresh" } };

describe("changesOf", () => {
  it("reads what a change did from the ops that undo it", () => {
    const changes = changesOf([
      { type: "EdgeRemoved", payload: { id: "e1" } },
      { type: "NodeRemoved", payload: { id: "fresh" } },
      { type: "NodeUpdated", payload: { id: "kept", fields: { label: "Hip hop" } } },
      { type: "NodeAdded", payload: { id: "gone", x: 400, y: 10, width: 120, height: 40, label: "Disco", data: {} } },
      { type: "EdgeAdded", payload: { id: "e0", source: "kept", target: "gone" } },
    ], nodes, edges);
    expect(changes.marks).toEqual([
      { id: "e1", element: "edge", kind: "added" },
      { id: "fresh", element: "node", kind: "added" },
      { id: "kept", element: "node", kind: "updated", was: "Hip hop" },
    ]);
    expect(changes.removed.nodes).toMatchObject([{ id: "gone", kind: "removed", x: 400, label: "Disco" }]);
    expect(changes.removed.edges).toEqual([{ id: "e0", kind: "removed", source: "kept", target: "gone" }]);
  });

  it("marks nothing the canvas no longer holds, and removes nothing it still does", () => {
    const changes = changesOf([
      { type: "NodeRemoved", payload: { id: "already-gone" } },
      { type: "NodeAdded", payload: { id: "kept", x: 0, y: 0 } },
    ], nodes, edges);
    expect(changes.marks).toEqual([]);
    expect(changes.removed.nodes).toEqual([]);
  });

  it("names no old label when only the data changed", () => {
    const changes = changesOf([
      { type: "NodeUpdated", payload: { id: "kept", fields: { data: { rows: [] } } } },
    ], nodes, edges);
    expect(changes.marks).toEqual([{ id: "kept", element: "node", kind: "updated" }]);
  });
});

describe("markChanges", () => {
  afterEach(() => markChanges([]));

  it("styles the real elements and takes the marks off again", () => {
    markChanges([
      { id: "fresh", element: "node", kind: "added", color: "rgb(37,99,235)", strong: false },
      { id: "kept", element: "node", kind: "updated", was: "Hip hop", color: "rgb(37,99,235)", strong: true },
      { id: "e1", element: "edge", kind: "added", color: "rgb(37,99,235)", strong: false },
    ]);
    const css = document.getElementById("anchor-change-marks")?.textContent ?? "";
    expect(css).toContain('.react-flow__node[data-id="fresh"]::after');
    expect(css).toContain('content: "new"');
    expect(css).toContain('content: "changed"');
    expect(css).toContain('content: "Hip hop"');
    expect(css).toContain(".react-flow__edge[data-id=\"e1\"] path:not(.react-flow__edge-interaction)");
    markChanges([]);
    expect(document.getElementById("anchor-change-marks")).toBeNull();
  });
});
