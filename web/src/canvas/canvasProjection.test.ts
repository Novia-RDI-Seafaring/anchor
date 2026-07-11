import { describe, expect, it } from "vitest";

import type { CanvasEdge, CanvasNode } from "@/stores/canvasStore";

import {
  ancestorOffset,
  canvasNodeSize,
  projectCanvasEdges,
  projectCanvasNode,
} from "./canvasProjection";

function node(id: string, fields: Partial<CanvasNode> = {}): CanvasNode {
  return {
    id,
    node_type: "concept",
    label: id,
    x: 0,
    y: 0,
    data: {},
    ...fields,
  };
}

function edge(id: string, fields: Partial<CanvasEdge> = {}): CanvasEdge {
  return {
    id,
    source: "spec",
    target: "doc",
    label: "",
    edge_type: "floating",
    data: {},
    ...fields,
  };
}

describe("canvas node projection", () => {
  it("converts absolute store coordinates to parent-relative flow coordinates", () => {
    const nodes = {
      grandparent: node("grandparent", { x: 10, y: 20 }),
      parent: node("parent", { x: 40, y: 50, parent: "grandparent" }),
      child: node("child", { x: 90, y: 120, parent: "parent" }),
    };

    expect(ancestorOffset("child", nodes)).toEqual({ x: 50, y: 70 });
    expect(projectCanvasNode(nodes.child, nodes)).toMatchObject({
      parentId: "parent",
      extent: "parent",
      position: { x: 40, y: 50 },
    });
  });

  it("stops a cyclic parent walk instead of looping", () => {
    const nodes = {
      a: node("a", { x: 10, y: 20, parent: "b" }),
      b: node("b", { x: 30, y: 40, parent: "a" }),
    };
    expect(ancestorOffset("a", nodes)).toEqual({ x: 40, y: 60 });
  });

  it("prefers top-level dimensions and keeps legacy data as fallback", () => {
    expect(canvasNodeSize(node("new", {
      width: 240,
      height: 160,
      data: { width: 100, height: 80 },
    }))).toEqual({ width: 240, height: 160 });
    expect(canvasNodeSize(node("legacy", {
      data: { width: 100, height: 80 },
    }))).toEqual({ width: 100, height: 80 });
  });

  it("projects structural display fields into ReactFlow", () => {
    const source = node("structured", {
      width: 240,
      height: 160,
      locked: true,
      visible: false,
      layer: "annotation",
      opacity: 0.4,
    });
    expect(projectCanvasNode(source, { structured: source })).toMatchObject({
      data: { width: 240, height: 160, locked: true },
      draggable: false,
      hidden: true,
      zIndex: 2,
      style: { opacity: 0.4 },
    });
  });

  it("keeps legacy data.locked behavior during the top-level transition", () => {
    const legacy = node("legacy", { data: { locked: true } });
    expect(projectCanvasNode(legacy, { legacy })).toMatchObject({
      data: { locked: true },
      draggable: false,
    });
  });

  it("lets the canvas-level read-only setting control unlocked nodes", () => {
    const unlocked = node("unlocked");
    expect(projectCanvasNode(unlocked, { unlocked })).not.toHaveProperty("draggable");
  });
});

describe("canvas edge projection", () => {
  it("activates a matching evidence edge and dims its sibling", () => {
    const nodes = {
      spec: node("spec", { node_type: "spec" }),
      doc: node("doc", { node_type: "document", data: { slug: "manual" } }),
    };
    const edges = {
      active: edge("active", {
        edge_type: "anchored",
        sourceHandle: "row:0:key",
        targetHandle: "region:r1",
        data: { kind: "evidence", source_ref: { page: 2, region_id: "r1" } },
      }),
      sibling: edge("sibling", {
        edge_type: "anchored",
        sourceHandle: "row:1:key",
        targetHandle: "region:r2",
        data: { kind: "evidence", source_ref: { page: 3, region_id: "r2" } },
      }),
    };

    const projected = projectCanvasEdges(nodes, edges, {
      hoveredSourceRef: { slug: "manual", page: 2, region_id: "r1" },
      hoveredNodeId: null,
      selectedEdgeId: "active",
    });

    expect(projected.find((item) => item.id === "active")).toMatchObject({
      type: "anchored",
      selected: true,
      data: { active: true, dimmed: false },
    });
    expect(projected.find((item) => item.id === "sibling")).toMatchObject({
      data: { active: false, dimmed: true },
      style: { opacity: 0.25 },
    });
  });
});
