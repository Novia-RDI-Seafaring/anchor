import { describe, expect, it } from "vitest";

import { CANVAS_EDGE_Z_INDEX, canvasNodeLayers } from "./layering";

describe("canvas layer order", () => {
  it("puts nested areas below edges and ordinary cards above them", () => {
    const layers = canvasNodeLayers({
      outer: { node_type: "area" },
      inner: { node_type: "area", parent: "outer" },
      deepest: { node_type: "area", parent: "inner" },
      card: { node_type: "concept", parent: "deepest" },
      unparented: { node_type: "fact" },
    });
    expect(layers.outer).toBeLessThan(layers.inner!);
    expect(layers.inner).toBeLessThan(layers.deepest!);
    expect(layers.deepest).toBeLessThan(CANVAS_EDGE_Z_INDEX);
    expect(layers.card).toBeGreaterThan(CANVAS_EDGE_Z_INDEX);
    expect(layers.unparented).toBeGreaterThan(CANVAS_EDGE_Z_INDEX);
  });

  it("preserves explicit background and annotation layers", () => {
    const layers = canvasNodeLayers({
      background: { node_type: "image", layer: "background" },
      card: { node_type: "concept" },
      annotation: { node_type: "fact", layer: "annotation" },
    });
    expect(layers.background).toBeLessThan(CANVAS_EDGE_Z_INDEX);
    expect(layers.card).toBeGreaterThan(CANVAS_EDGE_Z_INDEX);
    expect(layers.annotation).toBeGreaterThan(layers.card!);
  });

  it("keeps a background below edges even when its parent is a card", () => {
    const layers = canvasNodeLayers({
      parent: { node_type: "concept", layer: "annotation" },
      child: { node_type: "concept", layer: "background", parent: "parent" },
      card: { node_type: "fact", parent: "parent" },
    });
    expect(layers.child).toBeLessThan(CANVAS_EDGE_Z_INDEX);
    expect(layers.card).toBeGreaterThan(CANVAS_EDGE_Z_INDEX);
    expect(layers.parent).toBeGreaterThan(layers.card!);
  });

  it("remains finite for missing or cyclic parents", () => {
    const layers = canvasNodeLayers({
      missing: { node_type: "area", parent: "absent" },
      first: { node_type: "area", parent: "second" },
      second: { node_type: "area", parent: "first" },
      card: { node_type: "concept", parent: "first" },
    });
    for (const id of ["missing", "first", "second"]) {
      expect(Number.isFinite(layers[id])).toBe(true);
      expect(layers[id]).toBeLessThan(CANVAS_EDGE_Z_INDEX);
    }
    expect(layers.card).toBeGreaterThan(CANVAS_EDGE_Z_INDEX);
    expect(canvasNodeLayers({})).toEqual({});
  });
});
