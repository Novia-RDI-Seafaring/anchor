/**
 * threads.ts tests (#344) — the pure half of scoped-ask threads.
 *
 * Chip derivation by node types, bounding boxes, pin placement from
 * targets, item ordering, staleness, and the projection of a suggestion's
 * ops onto ghost elements (with client-id mapping).
 */
import { describe, expect, it } from "vitest";

import {
  boundingBox,
  chipsForSelection,
  ghostElementsFromOps,
  isStaleSuggestion,
  orderedItems,
  pinsForCanvas,
  referencedExistingIds,
  threadTitle,
} from "./threads";
import { CANVAS_EDGES, CANVAS_NODES, SUGGESTION_OPS, makeItem, makeThread } from "./fixtures";

describe("chipsForSelection", () => {
  it("spec → fill + verify, then the defaults", () => {
    expect(chipsForSelection(["spec"])).toEqual([
      "Fill the missing values from the documents",
      "Verify these against the source",
      "Make sense of this",
      "Name and group these",
    ]);
  });

  it("document → extract; chart → digitize", () => {
    expect(chipsForSelection(["document"])).toEqual([
      "Extract the specs into a table",
      "Make sense of this",
      "Name and group these",
    ]);
    expect(chipsForSelection(["chart"])).toEqual([
      "Digitize this curve",
      "Make sense of this",
      "Name and group these",
    ]);
  });

  it("two or more nodes add compare + consistency after the type chips", () => {
    expect(chipsForSelection(["spec", "document"])).toEqual([
      "Fill the missing values from the documents",
      "Verify these against the source",
      "Extract the specs into a table",
      "Compare these",
      "Check consistency",
      "Make sense of this",
      "Name and group these",
    ]);
    expect(chipsForSelection(["concept", "concept"])).toEqual([
      "Compare these",
      "Check consistency",
      "Make sense of this",
      "Name and group these",
    ]);
  });

  it("defaults alone for a single unknown type", () => {
    expect(chipsForSelection(["concept"])).toEqual(["Make sense of this", "Name and group these"]);
  });
});

describe("boundingBox", () => {
  it("spans the existing nodes, using top-level size then data size then the default", () => {
    const box = boundingBox(["n1", "n2", "missing"], CANVAS_NODES);
    expect(box).toEqual({ x: 10, y: 20, width: 270, height: 140 });
    const withData = boundingBox(["a"], {
      a: { id: "a", node_type: "concept", label: "", x: 0, y: 0, data: { width: 30, height: 10 } },
    });
    expect(withData).toEqual({ x: 0, y: 0, width: 30, height: 10 });
    expect(boundingBox(["n3"], CANVAS_NODES)).toEqual({ x: 500, y: 500, width: 100, height: 100 });
  });

  it("is null when none of the ids exist", () => {
    expect(boundingBox(["zzz"], CANVAS_NODES)).toBeNull();
  });
});

describe("pinsForCanvas", () => {
  it("anchors an open thread at the top-right of its targets' bounding box", () => {
    const pins = pinsForCanvas([makeThread()], "plant", CANVAS_NODES);
    expect(pins).toHaveLength(1);
    expect(pins[0]).toMatchObject({ x: 280, y: 20, threadIds: ["t1"], nodeIds: ["n1", "n2"] });
  });

  it("skips resolved threads, other canvases, and targets that no longer exist", () => {
    const pins = pinsForCanvas(
      [
        makeThread({ id: "done", status: "resolved" }),
        makeThread({ id: "elsewhere", targets: [{ workspace_id: "other", node_id: "n1" }] }),
        makeThread({ id: "gone", targets: [{ workspace_id: "plant", node_id: "zzz" }] }),
        makeThread({ id: "plain", targets: undefined }),
      ],
      "plant",
      CANVAS_NODES,
    );
    expect(pins).toEqual([]);
  });

  it("groups threads sharing an anchor into one pin, oldest first", () => {
    const pins = pinsForCanvas(
      [
        makeThread({ id: "later", created_at: 200 }),
        makeThread({ id: "earlier", created_at: 100 }),
        makeThread({ id: "solo", targets: [{ workspace_id: "plant", node_id: "n3" }] }),
      ],
      "plant",
      CANVAS_NODES,
    );
    expect(pins).toHaveLength(2);
    expect(pins.find((p) => p.x === 280)?.threadIds).toEqual(["earlier", "later"]);
    expect(pins.find((p) => p.x === 600)?.threadIds).toEqual(["solo"]);
  });

  it("anchors only to the targets that still exist", () => {
    const pins = pinsForCanvas(
      [makeThread({ targets: [{ workspace_id: "plant", node_id: "n1" }, { workspace_id: "plant", node_id: "zzz" }] })],
      "plant",
      CANVAS_NODES,
    );
    expect(pins[0]).toMatchObject({ x: 110, y: 20, nodeIds: ["n1"] });
  });
});

describe("items", () => {
  it("orders by created_at then id and titles from the ask text", () => {
    const thread = makeThread({
      items: [
        makeItem({ id: "b", created_at: 5 }),
        makeItem({ id: "a", created_at: 5 }),
        makeItem({ id: "c", created_at: 1 }),
      ],
    });
    expect(orderedItems(thread).map((i) => i.id)).toEqual(["c", "a", "b"]);
    expect(threadTitle(thread)).toBe("make sense of this");
    expect(threadTitle(makeThread({ payload: {} }))).toBe("Ask");
  });
});

describe("staleness", () => {
  it("collects referenced ids, excluding client ids minted in the batch", () => {
    expect(referencedExistingIds(SUGGESTION_OPS)).toEqual({
      nodeIds: ["n1", "n1", "n2"],
      edgeIds: ["e1"],
    });
  });

  it("marks a pending suggestion stale when a referenced element is gone", () => {
    const s = makeItem({ id: "s1", type: "suggestion", state: "pending", ops: SUGGESTION_OPS });
    expect(isStaleSuggestion(s, CANVAS_NODES, CANVAS_EDGES)).toBe(false);
    const { n2: _gone, ...without } = CANVAS_NODES;
    expect(isStaleSuggestion(s, without, CANVAS_EDGES)).toBe(true);
    expect(isStaleSuggestion(s, CANVAS_NODES, {})).toBe(true);
  });

  it("never marks applied / declined / superseded suggestions or other types", () => {
    for (const state of ["applied", "declined", "superseded"] as const) {
      const s = makeItem({ id: "s", type: "suggestion", state, ops: SUGGESTION_OPS });
      expect(isStaleSuggestion(s, {}, {})).toBe(false);
    }
    expect(isStaleSuggestion(makeItem({ id: "m", type: "message" }), {}, {})).toBe(false);
  });
});

describe("ghostElementsFromOps", () => {
  it("projects added / updated / removed nodes and edges, mapping client ids", () => {
    const g = ghostElementsFromOps(SUGGESTION_OPS, CANVAS_NODES, CANVAS_EDGES);
    expect(g.nodes.map((n) => [n.kind, n.id])).toEqual([
      ["node-added", "tmp-1"],
      ["node-updated", "n1"],
      ["node-removed", "n2"],
    ]);
    const added = g.nodes[0]!;
    expect(added.rect).toEqual({ x: 400, y: 40, width: 160, height: 72 });
    expect(added.label).toBe("Cooling loop");
    const updated = g.nodes[1]!;
    expect(updated.oldLabel).toBe("Pump");
    expect(updated.label).toBe("Pump P-101");
    expect(updated.fields).toEqual(["label"]);
    const removed = g.nodes[2]!;
    expect(removed.rect).toEqual({ x: 200, y: 120, width: 80, height: 40 });

    expect(g.edges.map((e) => e.kind)).toEqual(["edge-added", "edge-removed"]);
    // The added edge runs from n1's center to the ghost's center.
    expect(g.edges[0]!.from).toEqual({ x: 60, y: 45 });
    expect(g.edges[0]!.to).toEqual({ x: 480, y: 76 });
    // The removed edge runs between its real endpoints.
    expect(g.edges[1]!.from).toEqual({ x: 60, y: 45 });
    expect(g.edges[1]!.to).toEqual({ x: 240, y: 140 });
  });

  it("flags references to missing elements instead of throwing", () => {
    const g = ghostElementsFromOps(SUGGESTION_OPS, {}, {});
    expect(g.nodes.filter((n) => n.missing).map((n) => n.id)).toEqual(["n1", "n2"]);
    expect(g.edges.every((e) => e.missing)).toBe(true);
  });

  it("shows touched fields when an update carries no label change", () => {
    const g = ghostElementsFromOps(
      [{ type: "NodeUpdated", payload: { id: "n1", fields: { data: { x: 1 } } } }],
      CANVAS_NODES,
      CANVAS_EDGES,
    );
    expect(g.nodes[0]).toMatchObject({ kind: "node-updated", label: "Pump", fields: ["data"] });
    expect(g.nodes[0]!.oldLabel).toBeUndefined();
  });
});
