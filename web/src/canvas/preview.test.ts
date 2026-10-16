/**
 * A suggestion's ops, run forward into what the reader will see. The
 * failure this guards against: approving a summary of a change instead of
 * the change.
 */
import { describe, expect, it } from "vitest";

import { previewCentre, previewOps, type NodeLike } from "@/canvas/preview";

const dims: NodeLike = {
  id: "dims",
  x: 120,
  y: 819,
  width: 281,
  height: 229,
  label: "LKH-5 dimensions (mm)",
  data: {
    label: "LKH-5 dimensions (mm)",
    rows: [
      { key: "A", value: "158" },
      { key: "B", value: "70" },
      { key: "C", value: "22" },
      { key: "D", value: "189" },
      { key: "E", value: "42" },
    ],
  },
};
const root: NodeLike = { id: "root", x: 355, y: 391, width: 351, height: 182, label: "LKH-5" };
const nodes = { dims, root };

// The split as it was actually proposed: trim the card, add its other half,
// join the new half to the root.
const SPLIT = [
  {
    type: "NodeUpdated",
    payload: {
      id: "dims",
      fields: {
        data: {
          label: "LKH-5 dimensions (mm), A-B",
          rows: [
            { key: "A", value: "158" },
            { key: "B", value: "70" },
          ],
        },
      },
    },
  },
  {
    type: "NodeAdded",
    payload: {
      id: "dims-c-e",
      node_type: "spec",
      x: 120,
      y: 1098,
      width: 281,
      height: 150,
      data: {
        label: "LKH-5 dimensions (mm), C-E",
        rows: [
          { key: "C", value: "22" },
          { key: "D", value: "189" },
          { key: "E", value: "42" },
        ],
      },
    },
  },
  { type: "EdgeAdded", payload: { id: "e2", source: "root", target: "dims-c-e" } },
];

describe("previewing a suggestion", () => {
  it("shows the changed card as it will read, and what it read before", () => {
    const { nodes: out } = previewOps(SPLIT, nodes);
    const changed = out.find((n) => n.id === "dims")!;
    expect(changed.kind).toBe("updated");
    expect(changed.label).toBe("LKH-5 dimensions (mm), A-B");
    expect(changed.rows.map((r) => r.key)).toEqual(["A", "B"]);
    expect(changed.before!.rows.map((r) => r.key)).toEqual(["A", "B", "C", "D", "E"]);
    // Where it already is: the update moved nothing.
    expect([changed.x, changed.y]).toEqual([120, 819]);
  });

  it("shows the new card with its rows, where it will land", () => {
    const { nodes: out } = previewOps(SPLIT, nodes);
    const added = out.find((n) => n.id === "dims-c-e")!;
    expect(added.kind).toBe("added");
    expect(added.rows.map((r) => `${r.key}=${r.value}`)).toEqual(["C=22", "D=189", "E=42"]);
    expect([added.x, added.y, added.width, added.height]).toEqual([120, 1098, 281, 150]);
    expect(added.before).toBeUndefined();
  });

  it("draws the new edge, including to a node that only exists in the batch", () => {
    const preview = previewOps(SPLIT, nodes);
    expect(preview.edges).toEqual([{ id: "e2", kind: "added", source: "root", target: "dims-c-e" }]);
    // Its far end is the previewed card, not something on the canvas yet.
    expect(previewCentre("dims-c-e", preview, nodes)).toEqual({ x: 120 + 281 / 2, y: 1098 + 75 });
    expect(previewCentre("root", preview, nodes)).toEqual({ x: 355 + 351 / 2, y: 391 + 91 });
  });

  it("strikes a removed card through where it stands", () => {
    const { nodes: out } = previewOps([{ type: "NodeRemoved", payload: { id: "dims" } }], nodes);
    expect(out).toEqual([
      expect.objectContaining({ id: "dims", kind: "removed", x: 120, y: 819, label: "LKH-5 dimensions (mm)" }),
    ]);
  });

  it("shows nothing the server would refuse", () => {
    const { nodes: out, edges } = previewOps(
      [
        { type: "NodeUpdated", payload: { id: "ghost", fields: { label: "x" } } },
        { type: "EdgeAdded", payload: { id: "e9", source: "root", target: "nowhere" } },
      ],
      nodes,
    );
    expect(out).toEqual([]);
    expect(edges).toEqual([]);
  });

  it("keeps a card added then edited in the same batch as an addition", () => {
    const { nodes: out } = previewOps(
      [
        { type: "NodeAdded", payload: { id: "n", x: 0, y: 0, data: { label: "first" } } },
        { type: "NodeUpdated", payload: { id: "n", fields: { data: { label: "second" } } } },
      ],
      {},
    );
    expect(out).toEqual([expect.objectContaining({ id: "n", kind: "added", label: "second" })]);
  });

  it("marks missing node and edge targets stale without inventing a preview", () => {
    for (const op of [
      { type: "NodeUpdated", payload: { id: "gone", fields: { label: "x" } } },
      { type: "NodeRemoved", payload: { id: "gone" } },
      { type: "EdgeAdded", payload: { id: "e", source: "root", target: "gone" } },
      { type: "EdgeAdded", payload: { source: "root", target: "gone" } },
      { type: "EdgeUpdated", payload: { id: "gone", fields: { label: "x" } } },
      { type: "EdgeRemoved", payload: { id: "gone" } },
    ]) {
      expect(previewOps([op], nodes)).toEqual({ nodes: [], edges: [], stale: true });
    }
  });

  it("keeps existing targets and targets created earlier in the batch fresh", () => {
    expect(previewOps(SPLIT, nodes).stale).toBe(false);
    expect(previewOps([{ type: "EdgeAdded", payload: { source: "root", target: "dims" } }], nodes).stale).toBe(false);
    expect(previewOps([
      { type: "NodeAdded", payload: { id: "new", x: 0, y: 0 } },
      { type: "NodeUpdated", payload: { id: "new", fields: { label: "updated" } } },
      { type: "EdgeAdded", payload: { id: "new-edge", source: "root", target: "new" } },
      { type: "EdgeUpdated", payload: { id: "new-edge", fields: { label: "updated" } } },
      { type: "EdgeRemoved", payload: { id: "new-edge" } },
      { type: "NodeRemoved", payload: { id: "new" } },
    ], nodes).stale).toBe(false);
    const edges = [{ id: "existing", source: "root", target: "dims" }];
    expect(previewOps([{ type: "EdgeRemoved", payload: { id: "existing" } }], nodes, edges).stale).toBe(false);
    expect(edges).toEqual([{ id: "existing", source: "root", target: "dims" }]);
  });

  it("checks target existence in batch order and preserves the original ops", () => {
    const ops = [
      { type: "NodeRemoved", payload: { id: "dims" } },
      { type: "EdgeRemoved", payload: { id: "link" } },
    ];
    const original = structuredClone(ops);
    expect(previewOps(ops, nodes, [{ id: "link", source: "root", target: "dims" }]).stale).toBe(true);
    expect(ops).toEqual(original);
    expect(nodes.dims).toBe(dims);
  });

  it("marks an addition stale when its parent has disappeared, using batch order", () => {
    const child = { type: "NodeAdded", payload: { id: "child", parent: "parent", x: 10, y: 20 } };
    expect(previewOps([child], nodes)).toEqual({ nodes: [], edges: [], stale: true });
    expect(previewOps([{ type: "NodeAdded", payload: { parent: "parent", x: 10, y: 20 } }], nodes).stale).toBe(true);
    const parent = { type: "NodeAdded", payload: { id: "parent", x: 0, y: 0 } };
    expect(previewOps([parent, child], nodes).stale).toBe(false);
    expect(previewOps([parent, { type: "NodeRemoved", payload: { id: "parent" } }, child], nodes).stale).toBe(true);
    expect(previewOps([{ ...child, payload: { ...child.payload, parent: "root" } }], nodes).stale).toBe(false);
  });
});
