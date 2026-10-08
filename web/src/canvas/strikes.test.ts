/**
 * A cross over an edge, read as the edge to remove. The failure this guards
 * against: two short strokes on empty canvas arriving as nothing at all.
 */
import { describe, expect, it } from "vitest";

import type { Point } from "@/canvas/lasso";
import { describeStrikes, resolveStrikes, type EdgePath } from "@/canvas/strikes";

// An edge running from (100,100) down and right to (500,400), drawn as a
// few straight pieces the way a sampled curve is.
const edge: EdgePath = {
  id: "e1",
  source: "root",
  target: "dims",
  points: [
    { x: 100, y: 100 },
    { x: 200, y: 200 },
    { x: 300, y: 250 },
    { x: 400, y: 300 },
    { x: 500, y: 400 },
  ],
};

/** A hand-drawn-ish line from one point to another. */
function line(a: Point, b: Point): Point[] {
  return [a, { x: (a.x + b.x) / 2 + 2, y: (a.y + b.y) / 2 - 2 }, b];
}

describe("reading a cross over an edge as a strike", () => {
  it("names the edge under the crossing", () => {
    const cross = [line({ x: 270, y: 220 }, { x: 330, y: 280 }), line({ x: 330, y: 220 }, { x: 270, y: 280 })];
    expect(resolveStrikes(cross, [edge])).toEqual([
      { edge: "e1", source: "root", target: "dims", x: expect.any(Number), y: expect.any(Number) },
    ]);
  });

  it("forgives a cross that lands a little beside the line", () => {
    const cross = [line({ x: 270, y: 235 }, { x: 330, y: 295 }), line({ x: 330, y: 235 }, { x: 270, y: 295 })];
    expect(resolveStrikes(cross, [edge]).map((s) => s.edge)).toEqual(["e1"]);
  });

  it("ignores a cross drawn on open canvas", () => {
    const cross = [line({ x: 270, y: 420 }, { x: 330, y: 480 }), line({ x: 330, y: 420 }, { x: 270, y: 480 })];
    expect(resolveStrikes(cross, [edge])).toEqual([]);
  });

  it("ignores two strokes that only meet at their ends", () => {
    // A corner over the edge: a tick or an arrowhead, not a cross.
    const corner = [line({ x: 240, y: 190 }, { x: 300, y: 250 }), line({ x: 300, y: 250 }, { x: 360, y: 190 })];
    expect(resolveStrikes(corner, [edge])).toEqual([]);
  });

  it("ignores a single stroke across the edge, which may be pointing or cutting", () => {
    expect(resolveStrikes([line({ x: 270, y: 280 }, { x: 330, y: 220 })], [edge])).toEqual([]);
  });

  it("picks the nearer of two edges running close together", () => {
    const other: EdgePath = {
      id: "e2",
      source: "root",
      target: "range",
      points: [
        { x: 100, y: 140 },
        { x: 500, y: 440 },
      ],
    };
    // Crossing at (300,250): on e1, ~20 off e2.
    const cross = [line({ x: 270, y: 220 }, { x: 330, y: 280 }), line({ x: 330, y: 220 }, { x: 270, y: 280 })];
    expect(resolveStrikes(cross, [other, edge]).map((s) => s.edge)).toEqual(["e1"]);
  });

  it("says it in words an agent can act on without a picture", () => {
    const cross = [line({ x: 270, y: 220 }, { x: 330, y: 280 }), line({ x: 330, y: 220 }, { x: 270, y: 280 })];
    expect(describeStrikes(resolveStrikes(cross, [edge]))).toBe("strike out edge e1 (root -> dims)");
  });
});
