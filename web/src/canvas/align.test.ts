/**
 * align.ts unit tests — mirror the Python `tests/core/test_align.py`.
 * Same fixtures, same outcomes so a parity bug on either side surfaces fast.
 */
import { describe, expect, it } from "vitest";

import { alignNodes, distributeNodes, type SelectedNode } from "./align";

const n = (
  id: string, x: number, y: number,
  width?: number, height?: number,
): SelectedNode => ({ id, x, y, width, height });

describe("alignNodes", () => {
  it("returns an empty map for fewer than two nodes", () => {
    expect(alignNodes([n("a", 0, 0)], "top").size).toBe(0);
  });

  it("aligns top to min y", () => {
    const out = alignNodes(
      [n("a", 0, 10, 100, 100), n("b", 20, 30, 100, 100), n("c", 40, 5, 100, 100)],
      "top",
    );
    expect(Object.fromEntries(out)).toEqual({
      a: { x: 0, y: 5 },
      b: { x: 20, y: 5 },
    });
  });

  it("aligns bottom using max bottom edge (default size 100×100)", () => {
    const out = alignNodes(
      [n("a", 0, 0), n("b", 0, 50)],
      "bottom",
    );
    expect(Object.fromEntries(out)).toEqual({ a: { x: 0, y: 50 } });
  });

  it("aligns left to min x", () => {
    const out = alignNodes(
      [n("a", 10, 0), n("b", 50, 0), n("c", 100, 0)],
      "left",
    );
    expect(out.has("a")).toBe(false);
    expect(out.get("b")).toEqual({ x: 10, y: 0 });
    expect(out.get("c")).toEqual({ x: 10, y: 0 });
  });

  it("aligns right using max right edge", () => {
    const out = alignNodes(
      [n("a", 0, 0, 100, 100), n("b", 200, 0, 50, 50)],
      "right",
    );
    expect(out.get("a")).toEqual({ x: 150, y: 0 });
    expect(out.has("b")).toBe(false);
  });

  it("center-h centres y midline", () => {
    const out = alignNodes(
      [n("a", 0, 0, 100, 100), n("b", 0, 100, 100, 100)],
      "center-h",
    );
    expect(out.get("a")).toEqual({ x: 0, y: 50 });
    expect(out.get("b")).toEqual({ x: 0, y: 50 });
  });

  it("center-v centres x midline", () => {
    const out = alignNodes(
      [n("a", 0, 0, 100, 100), n("b", 200, 0, 100, 100)],
      "center-v",
    );
    expect(out.get("a")).toEqual({ x: 100, y: 0 });
    expect(out.get("b")).toEqual({ x: 100, y: 0 });
  });

  it("omits nodes already on the line", () => {
    const out = alignNodes(
      [n("a", 0, 5), n("b", 10, 5)],
      "top",
    );
    expect(out.size).toBe(0);
  });
});

describe("distributeNodes", () => {
  it("returns an empty map for fewer than three nodes", () => {
    expect(distributeNodes([n("a", 0, 0), n("b", 10, 0)], "horizontal").size).toBe(0);
  });

  it("distributes the middle node horizontally", () => {
    const out = distributeNodes(
      [n("a", 0, 0, 100, 100), n("b", 120, 0, 100, 100), n("c", 300, 0, 100, 100)],
      "horizontal",
    );
    expect(Object.fromEntries(out)).toEqual({ b: { x: 150, y: 0 } });
  });

  it("distributes the middle node vertically", () => {
    const out = distributeNodes(
      [n("a", 0, 0, 100, 100), n("b", 0, 120, 100, 100), n("c", 0, 300, 100, 100)],
      "vertical",
    );
    expect(Object.fromEntries(out)).toEqual({ b: { x: 0, y: 150 } });
  });

  it("endpoints do not move", () => {
    const out = distributeNodes(
      [n("a", 0, 0, 100, 100), n("b", 200, 0, 100, 100), n("c", 300, 0, 100, 100)],
      "horizontal",
    );
    expect(out.has("a")).toBe(false);
    expect(out.has("c")).toBe(false);
  });

  it("input order does not change the result (sort by centre)", () => {
    const out = distributeNodes(
      [n("c", 300, 0, 100, 100), n("a", 0, 0, 100, 100), n("b", 120, 0, 100, 100)],
      "horizontal",
    );
    expect(Object.fromEntries(out)).toEqual({ b: { x: 150, y: 0 } });
  });
});
