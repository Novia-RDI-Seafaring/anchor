/**
 * A drawn diagram, read as nodes and edges. The failure this guards against
 * is silent: five words arrive in draw order, four connectors vanish, and a
 * child reads as a sibling.
 */
import { describe, expect, it } from "vitest";

import { describeSketch, resolveSketch } from "@/canvas/sketch";
import type { Box, Point } from "@/canvas/lasso";

/** A closed shape, drawn roughly round the given box. */
function blob(cx: number, cy: number, r = 60): Point[] {
  const out: Point[] = [];
  for (let a = 0; a <= 360; a += 20) {
    const rad = (a * Math.PI) / 180;
    out.push({ x: cx + Math.cos(rad) * r, y: cy + Math.sin(rad) * r });
  }
  return out;
}

/** A line from one point to another, as a hand would draw it. */
function line(a: Point, b: Point): Point[] {
  return [a, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, b];
}

describe("reading a drawing as a diagram", () => {
  // The shape of the sketch that started this: a root, two children, one
  // grandchild, and one off to the side.
  const root = blob(500, 200);
  const dims = blob(200, 600);
  const drawing = blob(300, 900);
  const pump = blob(900, 300);
  const strokes = [
    root,
    dims,
    drawing,
    pump,
    line({ x: 470, y: 260 }, { x: 240, y: 545 }),
    line({ x: 240, y: 655 }, { x: 290, y: 845 }),
    line({ x: 560, y: 200 }, { x: 845, y: 290 }),
  ];
  const labels = [
    { text: "LKH-5", inStroke: 0 },
    { text: "Dimensions", inStroke: 1 },
    { text: "drawing", inStroke: 2 },
    { text: "pump info", inStroke: 3 },
  ];

  it("keeps the words with the shapes they were written in", () => {
    const sketch = resolveSketch(strokes, labels);
    expect(sketch.nodes.map((n) => n.label)).toEqual([
      "LKH-5",
      "Dimensions",
      "drawing",
      "pump info",
    ]);
  });

  it("recovers the connectors the word list threw away", () => {
    const { nodes, edges } = resolveSketch(strokes, labels);
    const name = (id: string) => nodes.find((n) => n.id === id)!.label;
    expect(edges.map((e) => `${name(e.from)}->${name(e.to)}`)).toEqual([
      "LKH-5->Dimensions",
      "Dimensions->drawing",
      "LKH-5->pump info",
    ]);
  });

  it("carries where everything was, so it can be rebuilt as drawn", () => {
    const sketch = resolveSketch(strokes, labels);
    const dimsNode = sketch.nodes.find((n) => n.label === "Dimensions")!;
    // Within a pixel: a shape sampled every 20 degrees never quite touches
    // its own extremes, and neither does a hand.
    expect(dimsNode.rect.x).toBeCloseTo(140, -1);
    expect(dimsNode.rect.y).toBeCloseTo(540, -1);
    // The grandchild sits below its parent, as it was drawn.
    const drawingNode = sketch.nodes.find((n) => n.label === "drawing")!;
    expect(drawingNode.rect.y).toBeGreaterThan(dimsNode.rect.y);
  });

  it("says the same thing in prose, for a reader that only gets text", () => {
    const text = describeSketch(resolveSketch(strokes, labels));
    expect(text).toContain("LKH-5 -> Dimensions");
    expect(text).toContain("Dimensions -> drawing");
  });

  it("invents no relation from a line that joins nothing", () => {
    const stray = [...strokes, line({ x: 1400, y: 1400 }, { x: 1600, y: 1500 })];
    expect(resolveSketch(stray, labels).edges).toHaveLength(3);
  });

  it("ignores a line that ends where it started", () => {
    const backToItself = [root, line({ x: 470, y: 200 }, { x: 530, y: 210 })];
    expect(resolveSketch(backToItself, [])).toMatchObject({ edges: [] });
  });

  it("counts a connector that stops just short of a shape", () => {
    const short = [root, dims, line({ x: 470, y: 260 }, { x: 250, y: 525 })];
    expect(resolveSketch(short, []).edges).toHaveLength(1);
  });

  it("names the canvas element a shape was drawn around", () => {
    const card: Box = { id: "lkh10-measures", x: 460, y: 160, width: 80, height: 80 };
    const sketch = resolveSketch([root], [], [card]);
    expect(sketch.nodes[0]!.encircles).toBe("lkh10-measures");
  });

  it("has nothing to say about an empty page", () => {
    expect(describeSketch({ nodes: [], edges: [] })).toBe("");
  });
});
