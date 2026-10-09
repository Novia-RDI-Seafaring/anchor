import { expect, it } from "vitest";

import { toRfNode } from "./CanvasGraph";
import { foldedGraph, structureSignature } from "./subtrees";

it("renders a shared child at its saved position when its actual container is folded away", () => {
  const nodes = {
    root: { id: "root", node_type: "concept", label: "Root", x: 0, y: 0, data: { collapsed: true } },
    container: { id: "container", node_type: "area", label: "Container", x: 100, y: 120 },
    other: { id: "other", node_type: "concept", label: "Other", x: 200, y: 0 },
    child: { id: "child", node_type: "fact", label: "Child", x: 500, y: 600, parent: "container" },
  };
  const edges = [{ source: "root", target: "container" }, { source: "other", target: "child" }];
  const { hidden } = foldedGraph(nodes, edges);
  expect(hidden.has("container")).toBe(true);
  expect(hidden.has("child")).toBe(false);
  expect(toRfNode(nodes.child, nodes, hidden)).toMatchObject({ position: { x: 500, y: 600 } });
  expect(toRfNode(nodes.child, nodes, hidden).parentId).toBeUndefined();
  expect(nodes.child.parent).toBe("container");
  expect(toRfNode(nodes.child, nodes, new Set())).toMatchObject({ parentId: "container", position: { x: 400, y: 480 } });
});

it("does not invalidate the topology projection for position or content edits", () => {
  const first = { a: { id: "a", node_type: "concept", x: 0, data: { collapsed: false, text: "A" } } };
  const moved = { a: { ...first.a, x: 900, data: { ...first.a.data, text: "B" } } };
  expect(structureSignature(first, [])).toBe(structureSignature(moved, []));
  expect(structureSignature({ a: { ...first.a, data: { collapsed: true } } }, [])).not.toBe(structureSignature(first, []));
});
