import { describe, expect, it } from "vitest";

import { absolutePosition, parentedNodeIds, planDragMoves, visibleParentId, visibleParentOffset, type GeometryNode } from "./geometry";

const nodes: Record<string, GeometryNode> = {
  outer: { id: "outer", x: 100, y: 80 },
  middle: { id: "middle", x: 150, y: 130, parent: "outer" },
  inner: { id: "inner", x: 180, y: 170, parent: "middle" },
  leaf: { id: "leaf", x: 220, y: 205, parent: "inner" },
  plain: { id: "plain", x: 600, y: 200 },
};
const byId = (moves: Array<GeometryNode>) => Object.fromEntries(moves.map((move) => [move.id, move]));

describe("canonical absolute canvas geometry", () => {
  it("composes deep parent-relative positions back to their saved absolute coordinates", () => {
    const rendered = new Map<string, { x: number; y: number }>();
    for (const node of Object.values(nodes)) {
      const offset = visibleParentOffset(node.id, nodes);
      const relative = { x: node.x - offset.x, y: node.y - offset.y };
      const parent = visibleParentId(node.id, nodes);
      const world = parent ? rendered.get(parent)! : { x: 0, y: 0 };
      rendered.set(node.id, { x: relative.x + world.x, y: relative.y + world.y });
      expect(rendered.get(node.id)).toEqual({ x: node.x, y: node.y });
      expect(absolutePosition(node.id, relative, nodes)).toEqual({ x: node.x, y: node.y });
    }
  });
  it("uses no parent offset for a rescued child, a missing parent, or a root", () => {
    const hidden = new Set(["inner"]);
    expect(visibleParentId("leaf", nodes, hidden)).toBeUndefined();
    expect(absolutePosition("leaf", { x: 220, y: 205 }, nodes, hidden)).toEqual({ x: 220, y: 205 });
    expect(absolutePosition("outer", { x: 120, y: 100 }, nodes)).toEqual({ x: 120, y: 100 });
    expect(visibleParentOffset("orphan", { orphan: { id: "orphan", x: 3, y: 4, parent: "missing" } })).toEqual({ x: 0, y: 0 });
  });
  it("converts a deeply nested leaf drag without summing absolute ancestors", () => {
    expect(planDragMoves(nodes, [{ id: "leaf", position: { x: 55, y: 40 } }])).toEqual([{ id: "leaf", x: 235, y: 210 }]);
  });
  it("translates all canonical descendants of a single dragged container once", () => {
    const before = structuredClone(nodes);
    const moves = byId(planDragMoves(nodes, [{ id: "outer", position: { x: 120, y: 70 } }]));
    expect(moves).toEqual({ outer: { id: "outer", x: 120, y: 70 }, middle: { id: "middle", x: 170, y: 120 }, inner: { id: "inner", x: 200, y: 160 }, leaf: { id: "leaf", x: 240, y: 195 } });
    expect(nodes).toEqual(before);
  });
  it("resolves parent-plus-child selections in either order with one world delta", () => {
    const dragged = [{ id: "outer", position: { x: 120, y: 70 } }, { id: "leaf", position: { x: 40, y: 35 } }];
    const expected = byId(planDragMoves(nodes, [dragged[0]!]));
    expect(byId(planDragMoves(nodes, dragged))).toEqual(expected);
    expect(byId(planDragMoves(nodes, [...dragged].reverse()))).toEqual(expected);
  });
  it("lets an explicitly moved nested container set its descendant delta", () => {
    const dragged = [{ id: "middle", position: { x: 60, y: 50 } }, { id: "outer", position: { x: 120, y: 70 } }];
    expect(byId(planDragMoves(nodes, dragged))).toEqual({ outer: { id: "outer", x: 120, y: 70 }, middle: { id: "middle", x: 180, y: 120 }, inner: { id: "inner", x: 210, y: 160 }, leaf: { id: "leaf", x: 250, y: 195 } });
  });
  it("moves folded descendants and preserves rescued children's canonical parent", () => {
    const hidden = new Set(["middle", "inner"]);
    expect(byId(planDragMoves(nodes, [{ id: "outer", position: { x: 120, y: 80 } }], hidden)).leaf).toEqual({ id: "leaf", x: 240, y: 205 });
    expect(planDragMoves(nodes, [{ id: "leaf", position: { x: 225, y: 210 } }], hidden)).toEqual([{ id: "leaf", x: 225, y: 210 }]);
    expect(nodes.leaf!.parent).toBe("inner");
  });
  it("ignores missing roots, unchanged drags and defensive parent cycles", () => {
    expect(planDragMoves(nodes, [{ id: "missing", position: { x: 0, y: 0 } }, { id: "leaf", position: { x: 40, y: 35 } }])).toEqual([]);
    const cycle = { a: { id: "a", x: 1, y: 2, parent: "b" }, b: { id: "b", x: 3, y: 4, parent: "a" } };
    expect(parentedNodeIds(cycle, ["a", "b"])).toEqual(["a", "b"]);
    const moves = planDragMoves(cycle, [{ id: "a", position: { x: 5, y: 6 } }]);
    expect(moves.every((move) => Number.isFinite(move.x) && Number.isFinite(move.y))).toBe(true);
    expect(new Set(moves.map((move) => move.id)).size).toBe(moves.length);
  });
});
