import { expect, it } from "vitest";

import { toRfNode } from "./CanvasGraph";
import { foldedGraph, structureSignature } from "./subtrees";

it("renders a deeply nested hierarchy at its canonical absolute positions", () => {
  const nodes = {
    outer: { id: "outer", node_type: "area", label: "Outer", x: 100, y: 100 },
    middle: { id: "middle", node_type: "area", label: "Middle", x: 150, y: 150, parent: "outer" },
    inner: { id: "inner", node_type: "area", label: "Inner", x: 180, y: 180, parent: "middle" },
    leaf: { id: "leaf", node_type: "fact", label: "Leaf", x: 210, y: 210, parent: "inner" },
  };
  for (const delta of [0, 5]) {
    const moved = Object.fromEntries(Object.values(nodes).map((node) => [node.id, { ...node, x: node.x + delta }]));
    const rendered = new Map<string, { x: number; y: number }>();
    for (const node of Object.values(moved)) {
      const flow = toRfNode(node, moved);
      const parent = flow.parentId ? rendered.get(flow.parentId)! : { x: 0, y: 0 };
      rendered.set(node.id, { x: flow.position.x + parent.x, y: flow.position.y + parent.y });
      expect(rendered.get(node.id)).toEqual({ x: node.x, y: node.y });
    }
  }
});
import { CANVAS_EDGE_Z_INDEX, canvasNodeLayers } from "./layering";

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

it("applies visual layers without changing nesting, dimensions or drag locks", () => {
  const nodes = {
    outer: { id: "outer", node_type: "area", label: "Outer", x: 100, y: 120 },
    inner: { id: "inner", node_type: "area", label: "Inner", x: 20, y: 30, parent: "outer" },
    card: { id: "card", node_type: "concept", label: "Card", x: 500, y: 600, parent: "inner",
      data: { width: 200, height: 90, locked: true } },
  };
  const layers = canvasNodeLayers(nodes);
  const area = toRfNode(nodes.inner, nodes, undefined, layers);
  const card = toRfNode(nodes.card, nodes, undefined, layers);
  expect(area.style?.zIndex).toBe(area.zIndex);
  expect(area.zIndex).toBeLessThan(CANVAS_EDGE_Z_INDEX);
  expect(area.draggable).toBe(true);
  expect(card.style?.zIndex).toBe(card.zIndex);
  expect(card.zIndex).toBeGreaterThan(CANVAS_EDGE_Z_INDEX);
  expect(card).toMatchObject({
    parentId: "inner", position: { x: 480, y: 570 }, draggable: false,
    data: { width: 200, height: 90 },
  });
});

it("keeps an explicit background below edges when its parent is an ordinary card", () => {
  const nodes = {
    parent: { id: "parent", node_type: "concept", label: "Parent", x: 100, y: 120 },
    background: { id: "background", node_type: "concept", label: "Background", x: 300, y: 320,
      parent: "parent", layer: "background" as const },
  };
  const background = toRfNode(nodes.background, nodes);
  expect(background).toMatchObject({ parentId: "parent", position: { x: 200, y: 200 } });
  expect(background.style?.zIndex).toBeLessThan(CANVAS_EDGE_Z_INDEX);
  expect(background.style?.zIndex).toBe(background.zIndex);
});
