/**
 * A line across a table, read as a row boundary. The failure this guards
 * against is the one that needed a screenshot five times: "split here" with
 * a card id and no idea where.
 */
import { describe, expect, it } from "vitest";

import { describeCuts, resolveCuts, type RowBand } from "@/canvas/cuts";
import type { Box, Point } from "@/canvas/lasso";

// A table 200 wide: 60 of title, five rows of 40, and 40 of footer below
// the last row -- so "inside the card but below every row" is a real place.
const card: Box = { id: "dims", x: 100, y: 100, width: 200, height: 300 };
const rows: RowBand[] = ["A", "B", "C", "D", "E"].map((key, i) => ({
  key,
  top: 160 + i * 40,
  bottom: 200 + i * 40,
}));
const rowsOf = (id: string) => (id === "dims" ? rows : null);

/** A hand-drawn-ish line from one point to another. */
function line(a: Point, b: Point): Point[] {
  return [a, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 + 3 }, b];
}

describe("reading a line across a table as a cut", () => {
  it("names the row above the gap the line went through", () => {
    // Straight through the B|C boundary at y=240.
    const cuts = resolveCuts([line({ x: 60, y: 240 }, { x: 340, y: 242 })], [card], rowsOf);
    expect(cuts).toEqual([{ node: "dims", after: "B", afterIndex: 1, y: expect.any(Number) }]);
  });

  it("snaps to the nearest gap when the hand lands a little into a row", () => {
    // 252 is inside C (240-280) but closer to B|C than to C|D.
    const cuts = resolveCuts([line({ x: 60, y: 252 }, { x: 340, y: 252 })], [card], rowsOf);
    expect(cuts[0]!.after).toBe("B");
  });

  it("ignores a line that only clips a corner", () => {
    const cuts = resolveCuts([line({ x: 60, y: 240 }, { x: 140, y: 240 })], [card], rowsOf);
    expect(cuts).toEqual([]);
  });

  it("ignores a steep stroke, which is pointing rather than dividing", () => {
    const cuts = resolveCuts([line({ x: 150, y: 120 }, { x: 250, y: 340 })], [card], rowsOf);
    expect(cuts).toEqual([]);
  });

  it("ignores a ring, and a line above the first row or below the last", () => {
    const ring: Point[] = [];
    for (let a = 0; a <= 360; a += 30) {
      const r = (a * Math.PI) / 180;
      ring.push({ x: 200 + Math.cos(r) * 80, y: 230 + Math.sin(r) * 80 });
    }
    expect(resolveCuts([ring], [card], rowsOf)).toEqual([]);
    expect(resolveCuts([line({ x: 60, y: 130 }, { x: 340, y: 130 })], [card], rowsOf)).toEqual([]);
    // 380 is inside the card's footer, below row E (320-360): nothing to divide.
    expect(resolveCuts([line({ x: 60, y: 380 }, { x: 340, y: 380 })], [card], rowsOf)).toEqual([]);
  });

  it("leaves a card whose rows it cannot see alone", () => {
    const other: Box = { id: "text", x: 100, y: 100, width: 200, height: 300 };
    expect(resolveCuts([line({ x: 60, y: 240 }, { x: 340, y: 240 })], [other], rowsOf)).toEqual([]);
  });

  it("says it in words an agent can act on without a picture", () => {
    const cuts = resolveCuts([line({ x: 60, y: 240 }, { x: 340, y: 240 })], [card], rowsOf);
    expect(describeCuts(cuts)).toBe("cut dims after row B");
  });
});
