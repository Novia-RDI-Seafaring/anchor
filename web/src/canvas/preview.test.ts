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
});
