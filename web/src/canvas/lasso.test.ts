/**
 * A stroke, resolved to the things it is about. The proposal is meant to be
 * corrected by hand, so it errs generous: one node too many costs a click,
 * while nothing at all leaves the reader wondering what they did wrong.
 */
import { describe, expect, it } from "vitest";

import {
  blobAround,
  calloutPlaces,
  clearSpot,
  leaderPath,
  pullStroke,
  rimReach,
  clipToBox,
  dropTarget,
  fitStroke,
  insidePolygon,
  insideStroke,
  isLoop,
  leaderAngle,
  loopAndTail,
  loopCentre,
  lassoHits,
  markHits,
  nearestOnStroke,
  pivotStroke,
  rectFrom,
  ringOutline,
  smoothClosedPath,
  rectsOverlap,
  remapStroke,
  strokeAt,
  strokeBounds,
  lineOutOfLoop,
  strokeHeading,
  flowAway,
  strokeLength,
  toggleId,
  translateStroke,
  unionRect,
  type Box,
  type Point,
  type Callout,
  type Rect,
} from "@/canvas/lasso";

const A: Box = { id: "a", x: 0, y: 0, width: 100, height: 50 };
const B: Box = { id: "b", x: 200, y: 0, width: 100, height: 50 };
const C: Box = { id: "c", x: 0, y: 200, width: 100, height: 50 };
const ALL = [A, B, C];

/** A rough ring around (cx, cy), as a hand would draw it. */
function ring(cx: number, cy: number, r: number, gap = 0.15) {
  const pts = [];
  for (let t = 0; t <= Math.PI * 2 - gap; t += 0.3) {
    pts.push({ x: cx + Math.cos(t) * r, y: cy + Math.sin(t) * r });
  }
  return pts;
}

describe("telling a ring from a line", () => {
  it("reads a hand-drawn ring as a loop even with a gap in it", () => {
    expect(isLoop(ring(50, 25, 80))).toBe(true);
  });

  it("does not read a straight stroke as a loop", () => {
    expect(isLoop([{ x: 0, y: 0 }, { x: 300, y: 0 }, { x: 600, y: 0 }, { x: 900, y: 0 }])).toBe(false);
  });

  it("judges closure against the stroke's own size, not a fixed distance", () => {
    // The same gesture must read the same whether it rings one cell or a
    // whole column.
    expect(isLoop(ring(50, 25, 20))).toBe(true);
    expect(isLoop(ring(50, 25, 400))).toBe(true);
  });

  it("is not fooled by a stroke that doubles back without going anywhere", () => {
    expect(isLoop([{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 0 }])).toBe(false);
  });

  it("measures the path, not the distance between the ends", () => {
    expect(strokeLength([{ x: 0, y: 0 }, { x: 3, y: 4 }, { x: 3, y: 0 }])).toBeCloseTo(9);
  });
});

describe("what a loop proposes", () => {
  it("takes what its enclosed area touches", () => {
    expect(lassoHits(ring(50, 25, 90), ALL)).toEqual(["a"]);
  });

  it("counts a node only half inside the ring", () => {
    // A reviewer who drew around something meant it, even if the pen clipped.
    const half = ring(100, 25, 70);
    expect(lassoHits(half, ALL)).toContain("a");
  });

  it("takes everything a big ring encloses", () => {
    expect(lassoHits(ring(120, 120, 400), ALL).sort()).toEqual(["a", "b", "c"]);
  });

  it("points at the node it was drawn inside", () => {
    // A small ring scribbled in the middle of a large card is about that card.
    const big: Box = { id: "big", x: 0, y: 0, width: 1000, height: 1000 };
    expect(lassoHits(ring(500, 500, 30), [big])).toEqual(["big"]);
  });
});

describe("what an open stroke proposes", () => {
  it("takes what it crosses, so underlining a card gives you that card", () => {
    const underline = [{ x: -20, y: 25 }, { x: 60, y: 25 }, { x: 130, y: 25 }];
    expect(lassoHits(underline, ALL)).toEqual(["a"]);
  });

  it("takes several when it sweeps across them", () => {
    const sweep = [{ x: -20, y: 25 }, { x: 150, y: 25 }, { x: 320, y: 25 }];
    expect(lassoHits(sweep, ALL).sort()).toEqual(["a", "b"]);
  });

  it("takes nothing when it crosses nothing", () => {
    expect(lassoHits([{ x: 0, y: 500 }, { x: 300, y: 500 }], ALL)).toEqual([]);
  });

  it("degrades a half-formed ring into the stroke rule instead of nothing", () => {
    // The whole point of having no cliff between the two behaviours: a ring
    // that did not close still gives the reader what they drew across.
    // An arc tight enough to pass through the card, left too open to close.
    const openArc = ring(50, 25, 40, 2.5);
    expect(isLoop(openArc)).toBe(false);
    expect(lassoHits(openArc, ALL)).toContain("a");
  });
});

describe("a tap is not a gesture", () => {
  it("proposes nothing for a click that went nowhere", () => {
    expect(lassoHits([{ x: 50, y: 25 }, { x: 51, y: 25 }], ALL)).toEqual([]);
  });

  it("proposes nothing for a single point", () => {
    expect(lassoHits([{ x: 50, y: 25 }], ALL)).toEqual([]);
  });
});

describe("correcting the proposal by hand", () => {
  it("adds one the stroke missed and removes one it caught", () => {
    expect(toggleId(["a"], "b")).toEqual(["a", "b"]);
    expect(toggleId(["a", "b"], "a")).toEqual(["b"]);
  });

  it("leaves the original alone", () => {
    const ids = ["a"];
    toggleId(ids, "b");
    expect(ids).toEqual(["a"]);
  });
});

describe("a mark made of several strokes", () => {
  it("keeps a connecting line as ink rather than a selection", () => {
    // Ring the value, draw across to a clear patch, write there. If the line
    // selected too, the mark would claim to be about every card it crossed.
    const circleA = ring(50, 25, 40);
    const lineAcross = [{ x: 50, y: 25 }, { x: 250, y: 25 }, { x: 450, y: 25 }];
    expect(lassoHits(lineAcross, ALL)).toContain("b");
    expect(markHits([circleA, lineAcross], ALL)).toEqual(["a"]);
  });

  it("picks up both when two things are ringed in turn", () => {
    expect(markHits([ring(50, 25, 40), ring(250, 25, 40)], ALL).sort()).toEqual(["a", "b"]);
  });

  it("lets the first stroke select whatever its shape", () => {
    // Underlining a card and then writing still targets that card.
    const underline = [{ x: -20, y: 25 }, { x: 60, y: 25 }, { x: 130, y: 25 }];
    expect(markHits([underline], ALL)).toEqual(["a"]);
  });

  it("catches the card a later line starts or ends on, not the ones it crosses", () => {
    // Two boxes drawn on open canvas first, then a line out of card A to
    // somewhere past card B. A is what the line is about; B is only on the way.
    const boxOne = ring(700, 300, 30);
    const boxTwo = ring(900, 300, 30);
    const outOfA = [{ x: 50, y: 25 }, { x: 250, y: 25 }, { x: 650, y: 25 }];
    expect(markHits([boxOne, boxTwo, outOfA], ALL)).toEqual(["a"]);
  });

  it("does not list the same thing twice when strokes overlap", () => {
    expect(markHits([ring(50, 25, 40), ring(50, 25, 45)], ALL)).toEqual(["a"]);
  });

  it("is empty for a mark that caught nothing", () => {
    expect(markHits([[{ x: 0, y: 500 }, { x: 300, y: 500 }]], ALL)).toEqual([]);
  });
});

describe("picking a drawn stroke back up", () => {
  const line = [{ x: 0, y: 0 }, { x: 100, y: 0 }];
  const far = [{ x: 0, y: 500 }, { x: 100, y: 500 }];

  it("finds the stroke under the point", () => {
    expect(strokeAt({ x: 50, y: 3 }, [line, far], 8)).toBe(0);
  });

  it("allows for aim, since a hairline cannot be hit exactly", () => {
    expect(strokeAt({ x: 50, y: 7 }, [line], 8)).toBe(0);
    expect(strokeAt({ x: 50, y: 40 }, [line], 8)).toBe(-1);
  });

  it("picks the most recent when strokes overlap", () => {
    expect(strokeAt({ x: 50, y: 0 }, [line, [{ x: 0, y: 0 }, { x: 100, y: 1 }]], 8)).toBe(1);
  });

  it("finds nothing where nothing was drawn", () => {
    expect(strokeAt({ x: 500, y: 500 }, [line], 8)).toBe(-1);
  });
});

describe("writing inside a shape that was drawn", () => {
  it("knows a point inside a closed shape", () => {
    expect(insideStroke({ x: 50, y: 25 }, ring(50, 25, 60))).toBe(true);
    expect(insideStroke({ x: 400, y: 25 }, ring(50, 25, 60))).toBe(false);
  });

  it("does not treat an open line as a container", () => {
    expect(insideStroke({ x: 50, y: 0 }, [{ x: 0, y: 0 }, { x: 100, y: 0 }])).toBe(false);
  });

  it("gives the shape's bounds, so text can sit within it", () => {
    const b = strokeBounds([{ x: 10, y: 20 }, { x: 110, y: 20 }, { x: 110, y: 70 }]);
    expect(b).toEqual({ x: 10, y: 20, width: 100, height: 50 });
  });
});

describe("which way the words flow", () => {
  const from = { x: 100, y: 100 };

  it("hangs text from its right edge when the line went left", () => {
    // Dragging left is a statement about wanting room on the left.
    expect(flowAway(from, { x: 20, y: 100 }).align).toBe("right");
    expect(flowAway(from, { x: 200, y: 100 }).align).toBe("left");
  });

  it("sits text on its bottom when the line went up", () => {
    expect(flowAway(from, { x: 100, y: 20 }).vAlign).toBe("bottom");
    expect(flowAway(from, { x: 100, y: 200 }).vAlign).toBe("top");
  });

  it("reads both axes at once for a diagonal", () => {
    expect(flowAway(from, { x: 10, y: 10 })).toEqual({ align: "right", vAlign: "bottom" });
  });
});

describe("nearestOnStroke", () => {
  it("lands on the ink rather than the corner of the box around it", () => {
    // A ring: its bounding corner sits well outside the curve.
    const ring: Point[] = [];
    for (let a = 0; a <= 360; a += 10) {
      const r = (a * Math.PI) / 180;
      ring.push({ x: 100 + Math.cos(r) * 50, y: 100 + Math.sin(r) * 50 });
    }
    const b = strokeBounds(ring);
    const corner = { x: b.x + b.width, y: b.y };
    const at = nearestOnStroke(ring, corner);
    // On the circle, to within the resolution of the polyline.
    expect(Math.hypot(at.x - 100, at.y - 100)).toBeCloseTo(50, 0);
    // And genuinely closer to the corner than the far side is.
    expect(Math.hypot(at.x - corner.x, at.y - corner.y)).toBeLessThan(
      Math.hypot(b.x - corner.x, b.y + b.height - corner.y),
    );
  });

  it("falls back to the target when there is no stroke", () => {
    expect(nearestOnStroke([], { x: 4, y: 7 })).toEqual({ x: 4, y: 7 });
  });
});

describe("fitStroke", () => {
  const shape: Point[] = [
    { x: 10, y: 10 },
    { x: 30, y: 12 },
    { x: 28, y: 30 },
    { x: 11, y: 28 },
  ];

  it("stretches the ink into the new box, wobble and all", () => {
    const out = fitStroke(shape, { x: 10, y: 10, width: 40, height: 40 });
    const b = strokeBounds(out);
    expect(b.width).toBeCloseTo(40);
    expect(b.height).toBeCloseTo(40);
    // Still hand-drawn: the second point is not flush with the top edge.
    expect(out[1]!.y).toBeGreaterThan(b.y);
  });

  it("grows downward when only the height changes", () => {
    const b = strokeBounds(shape);
    const out = fitStroke(shape, { ...b, height: b.height * 2 });
    expect(strokeBounds(out).y).toBeCloseTo(b.y);
    expect(strokeBounds(out).height).toBeCloseTo(b.height * 2);
  });

  it("keeps a flat stroke in place instead of collapsing it", () => {
    const flat: Point[] = [
      { x: 0, y: 5 },
      { x: 20, y: 5 },
    ];
    const out = fitStroke(flat, { x: 0, y: 5, width: 40, height: 10 });
    expect(out.map((p) => p.y)).toEqual([5, 5]);
    expect(out[1]!.x).toBeCloseTo(40);
  });
});

describe("rubber band geometry", () => {
  it("makes the same box whichever way the drag went", () => {
    const a = rectFrom({ x: 10, y: 10 }, { x: 40, y: 50 });
    const b = rectFrom({ x: 40, y: 50 }, { x: 10, y: 10 });
    expect(a).toEqual(b);
    expect(a).toEqual({ x: 10, y: 10, width: 30, height: 40 });
  });

  it("counts a mark the band merely touches", () => {
    const band = { x: 0, y: 0, width: 20, height: 20 };
    expect(rectsOverlap(band, { x: 15, y: 15, width: 100, height: 100 })).toBe(true);
    expect(rectsOverlap(band, { x: 21, y: 0, width: 5, height: 5 })).toBe(false);
  });

  it("takes every mark into one box", () => {
    expect(
      unionRect([
        { x: 10, y: 0, width: 10, height: 10 },
        { x: 0, y: 30, width: 5, height: 5 },
      ]),
    ).toEqual({ x: 0, y: 0, width: 20, height: 35 });
    expect(unionRect([])).toBeNull();
  });
});

describe("moving and scaling a group", () => {
  const one: Point[] = [
    { x: 0, y: 0 },
    { x: 10, y: 10 },
  ];
  const two: Point[] = [
    { x: 90, y: 90 },
    { x: 100, y: 100 },
  ];
  const group = { x: 0, y: 0, width: 100, height: 100 };

  it("keeps each mark's place in the group when the group scales", () => {
    const to = { x: 0, y: 0, width: 200, height: 200 };
    // The corner stroke stays in the corner rather than filling the box.
    expect(remapStroke(one, group, to)).toEqual([
      { x: 0, y: 0 },
      { x: 20, y: 20 },
    ]);
    expect(remapStroke(two, group, to)[1]).toEqual({ x: 200, y: 200 });
  });

  it("moves without resizing", () => {
    expect(translateStroke(one, 5, -5)).toEqual([
      { x: 5, y: -5 },
      { x: 15, y: 5 },
    ]);
  });
});

describe("leaderAngle", () => {
  const o = { x: 0, y: 0 };

  it("keeps rightward text on the line's own angle", () => {
    expect(leaderAngle(o, { x: 10, y: 10 })).toEqual({ deg: 45, flip: false });
    expect(leaderAngle(o, { x: 10, y: -10 })).toEqual({ deg: -45, flip: false });
  });

  it("never stands the words on their head", () => {
    // Every direction, including the ones pointing back to the left.
    for (let a = -180; a <= 180; a += 15) {
      const r = (a * Math.PI) / 180;
      const { deg } = leaderAngle(o, { x: Math.cos(r) * 50, y: Math.sin(r) * 50 });
      expect(Math.abs(deg)).toBeLessThanOrEqual(90.0001);
    }
  });

  it("hangs leftward text off its far edge so it still runs with the line", () => {
    const back = leaderAngle(o, { x: -10, y: 10 });
    expect(back.flip).toBe(true);
    // 135 degrees turned back the right way up is -45.
    expect(back.deg).toBeCloseTo(-45);
  });
});

describe("strokeHeading", () => {
  it("reads the direction the line was travelling, not the last jitter", () => {
    const line: Point[] = [
      { x: 0, y: 0 },
      { x: 30, y: -30 },
      { x: 60, y: -60 },
      // A wobble at the very end, as a hand lifting off leaves.
      { x: 61, y: -59 },
    ];
    const { end, from } = strokeHeading(line, 24);
    expect(end).toEqual({ x: 61, y: -59 });
    // Looking back far enough, the heading is still up and to the right.
    expect(from.x).toBeLessThan(end.x);
    expect(from.y).toBeGreaterThan(end.y);
    const { deg, flip } = leaderAngle(from, end);
    expect(flip).toBe(false);
    expect(deg).toBeLessThan(0);
  });

  it("survives a stroke with nothing to look back at", () => {
    const { end, from } = strokeHeading([{ x: 5, y: 5 }]);
    expect(end).toEqual({ x: 5, y: 5 });
    expect(from).toEqual({ x: 5, y: 5 });
  });
});

describe("pivotStroke", () => {
  const line: Point[] = [
    { x: 0, y: 0 },
    { x: 5, y: 2 },
    { x: 10, y: 0 },
  ];

  it("lands the far end exactly where it was dragged", () => {
    const out = pivotStroke(line, { x: 0, y: 20 });
    expect(out[0]).toEqual({ x: 0, y: 0 });
    expect(out[2]!.x).toBeCloseTo(0);
    expect(out[2]!.y).toBeCloseTo(20);
  });

  it("swings the wobble round with it instead of flattening it", () => {
    const out = pivotStroke(line, { x: 0, y: 20 });
    // The middle point sat off the line; it still does, on the other axis.
    expect(Math.abs(out[1]!.x)).toBeGreaterThan(1);
  });

  it("lengthens the whole stroke when the end is pulled further out", () => {
    const out = pivotStroke(line, { x: 20, y: 0 });
    expect(out[1]).toEqual({ x: 10, y: 4 });
  });

  it("leaves a stroke with nowhere to point alone", () => {
    const dot: Point[] = [
      { x: 3, y: 3 },
      { x: 3, y: 3 },
    ];
    expect(pivotStroke(dot, { x: 9, y: 9 })).toEqual(dot);
  });
});

describe("dropping a line on something", () => {
  const card: Box = { id: "card", x: 100, y: 0, width: 80, height: 40 };
  const region: Box = { id: "region", x: 0, y: -50, width: 400, height: 200 };

  it("takes the box the line stopped at, not one it passed over", () => {
    const across: Point[] = [
      { x: 110, y: 20 },
      { x: 300, y: 20 },
      { x: 320, y: 300 },
    ];
    expect(dropTarget(across, [card], 10)).toBeNull();
  });

  it("counts stopping just short of the edge", () => {
    const upTo: Point[] = [
      { x: 0, y: 20 },
      { x: 94, y: 20 },
    ];
    expect(dropTarget(upTo, [card], 10)?.id).toBe("card");
    expect(dropTarget(upTo, [card], 2)).toBeNull();
  });

  it("prefers the smaller box when one sits inside another", () => {
    const into: Point[] = [
      { x: 0, y: 20 },
      { x: 140, y: 20 },
    ];
    expect(dropTarget(into, [region, card], 10)?.id).toBe("card");
  });

  it("trims the tail to the edge it met", () => {
    const into: Point[] = [
      { x: 0, y: 20 },
      { x: 140, y: 20 },
    ];
    const out = clipToBox(into, card);
    expect(out).toHaveLength(2);
    expect(out[1]!.x).toBeCloseTo(100, 1);
    expect(out[1]!.y).toBeCloseTo(20, 1);
  });

  it("leaves a stroke that never arrived alone", () => {
    const past: Point[] = [
      { x: 0, y: 300 },
      { x: 400, y: 300 },
    ];
    expect(clipToBox(past, card)).toEqual(past);
  });
});

describe("a ring with a tail", () => {
  // A circle drawn from its right-hand side, closing, then a line out east.
  const ring: Point[] = [];
  for (let a = 0; a <= 360; a += 20) {
    const r = (a * Math.PI) / 180;
    ring.push({ x: 100 + Math.cos(r) * 30, y: 100 + Math.sin(r) * 30 });
  }
  const tail: Point[] = [
    { x: 130, y: 100 },
    { x: 180, y: 100 },
    { x: 230, y: 100 },
  ];
  const stroke = [...ring, ...tail.slice(1)];

  it("splits the ring from the line that leaves it", () => {
    const parts = loopAndTail(stroke);
    expect(parts).not.toBeNull();
    // The ring's own points all sit about 30 from the centre.
    for (const p of parts!.loop) {
      expect(Math.hypot(p.x - 100, p.y - 100)).toBeCloseTo(30, 0);
    }
    expect(parts!.tail[parts!.tail.length - 1]).toEqual({ x: 230, y: 100 });
  });

  it("finds the eye", () => {
    const { loop } = loopAndTail(stroke)!;
    const c = loopCentre(loop);
    expect(c.x).toBeCloseTo(100, 0);
    expect(c.y).toBeCloseTo(100, 0);
  });

  it("leaves a ring with no tail alone", () => {
    expect(loopAndTail(ring)).toBeNull();
  });

  it("keeps only the part of the tail that left the ring", () => {
    const { loop, tail: t } = loopAndTail(stroke)!;
    const line = lineOutOfLoop(loop, t);
    // Starts on the ring's edge, not inside it and not at its centre.
    expect(Math.hypot(line[0]!.x - 100, line[0]!.y - 100)).toBeCloseTo(30, 0);
    // Nothing left curling about inside the ring.
    for (const p of line) {
      expect(Math.hypot(p.x - 100, p.y - 100)).toBeGreaterThanOrEqual(29.9);
    }
    expect(line[line.length - 1]).toEqual({ x: 230, y: 100 });
  });

  it("gives nothing back for a tail that never got out", () => {
    const { loop } = loopAndTail(stroke)!;
    expect(lineOutOfLoop(loop, [{ x: 100, y: 100 }])).toEqual([]);
  });
});

describe("ringOutline", () => {
  it("smooths a dent out of the shape the reader sees", () => {
    // A box with a deep notch cut into its right edge.
    const dented: Point[] = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 50, y: 50 },
      { x: 100, y: 100 },
      { x: 0, y: 100 },
    ];
    const hull = ringOutline(dented);
    expect(hull).toHaveLength(4);
    expect(hull.some((p) => p.x === 50 && p.y === 50)).toBe(false);
  });

  it("starts a line on the outline, never inside the dent", () => {
    const dented: Point[] = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 50, y: 50 },
      { x: 100, y: 100 },
      { x: 0, y: 100 },
    ];
    // A tail leaving from the bottom of the notch, heading out to the right.
    const tail: Point[] = [
      { x: 50, y: 50 },
      { x: 80, y: 50 },
      { x: 300, y: 50 },
    ];
    const line = lineOutOfLoop(dented, tail);
    // Nothing left inside the shape: the line starts at the right edge.
    expect(line[0]!.x).toBeCloseTo(100, 0);
    expect(line[line.length - 1]).toEqual({ x: 300, y: 50 });
  });
});

describe("clearSpot", () => {
  const label = { width: 100, height: 40 };

  it("goes out to the side when everything is empty", () => {
    const at = clearSpot({ x: 0, y: 0 }, 100, 10, label, [], 10);
    expect(at.x).toBeGreaterThan(0);
    expect(Math.abs(at.y)).toBeLessThan(1);
  });

  it("goes elsewhere when the side is taken", () => {
    const blocked: Rect = { x: 50, y: -300, width: 300, height: 600 };
    const at = clearSpot({ x: 0, y: 0 }, 100, 10, label, [blocked], 10);
    expect(overlaps(at, blocked)).toBe(false);
  });

  it("stays a short line out from the rim rather than flying off", () => {
    const at = clearSpot({ x: 0, y: 0 }, 100, 10, label, [], 10);
    expect(Math.hypot(at.x, at.y)).toBeLessThanOrEqual(110);
  });

  it("measures from the rim, so a wide ring gets the same short leader as a small one", () => {
    // Twice as wide as it is tall: the rim is 200 out sideways, 100 up.
    const wide = (deg: number) => (Math.abs(Math.cos((deg * Math.PI) / 180)) > 0.5 ? 200 : 100);
    const at = clearSpot({ x: 0, y: 0 }, wide, 10, label, [], 10);
    expect(at.x).toBeCloseTo(210, 5);
    expect(Math.abs(at.y)).toBeLessThan(1);
  });

  it("goes out past a card it is sitting on rather than dropping below it", () => {
    // A ring near the right-hand edge of a wide card: there is open canvas
    // just to the right, and the offer should take it.
    const card: Rect = { x: -500, y: -200, width: 560, height: 400 };
    const at = clearSpot({ x: 0, y: 0 }, 100, 10, label, [card], 10);
    expect(at.x).toBeGreaterThan(0);
    expect(overlaps(at, card)).toBe(false);
  });

  it("leaves the rim on open canvas, not from inside a card the ring covers", () => {
    // A card under the right half of the ring: the rim there is inside it.
    const card: Rect = { x: 50, y: -150, width: 350, height: 300 };
    const at = clearSpot({ x: 0, y: 0 }, 100, 10, label, [card], 10);
    expect(at.x).toBeLessThan(0);
    expect(overlaps(at, card)).toBe(false);
  });

  it("gives the least cluttered spot when nowhere is clear", () => {
    const everywhere: Rect = { x: -9999, y: -9999, width: 99999, height: 99999 };
    const at = clearSpot({ x: 0, y: 0 }, 100, 10, label, [everywhere], 10);
    expect(Number.isFinite(at.x)).toBe(true);
    expect(Number.isFinite(at.y)).toBe(true);
  });

  function overlaps(at: Point, r: Rect): boolean {
    // The words run away from the leader, so the box hangs off the point
    // rather than straddling it -- the same rule clearSpot judges by.
    const box = {
      x: at.x < 0 ? at.x - label.width : at.x,
      y: at.y - label.height / 2,
      width: label.width,
      height: label.height,
    };
    return (
      box.x < r.x + r.width &&
      r.x < box.x + box.width &&
      box.y < r.y + r.height &&
      r.y < box.y + box.height
    );
  }
});

describe("a leader that lands level", () => {
  const controls = (d: string) => d.match(/-?[\d.]+/g)!.map(Number);

  it("arrives at the words horizontally, from the side they run away from", () => {
    const d = leaderPath({ x: 0, y: 0 }, { x: 100, y: -80 });
    const [, , , , c2x, c2y, bx, by] = controls(d);
    expect([bx, by]).toEqual([100, -80]);
    expect(c2y).toBe(-80);
    expect(c2x).toBeLessThan(100);
  });

  it("comes in from the right when the words run left", () => {
    const [, , , , c2x, c2y] = controls(leaderPath({ x: 0, y: 0 }, { x: -100, y: 30 }));
    expect(c2y).toBe(30);
    expect(c2x).toBeGreaterThan(-100);
  });

  it("still hooks in level when the words are straight above", () => {
    const [, , , , c2x, c2y] = controls(leaderPath({ x: 0, y: 0 }, { x: 0, y: -60 }));
    expect(c2y).toBe(-60);
    expect(c2x).toBeLessThan(0);
  });
});

describe("pulling on a stroke", () => {
  const ring: Point[] = [];
  for (let a = 0; a <= 360; a += 10) {
    const r = (a * Math.PI) / 180;
    ring.push({ x: Math.cos(r) * 100, y: Math.sin(r) * 100 });
  }
  const circumference = 2 * Math.PI * 100;

  it("moves the grabbed point the whole way and the far side not at all", () => {
    const pulled = pullStroke(ring, { x: 100, y: 0 }, { x: 40, y: 0 }, circumference / 4);
    expect(pulled[0]!.x).toBeCloseTo(140, 0);
    // The point opposite (180 degrees) is half the way round: untouched.
    const opposite = pulled[18]!;
    expect(opposite.x).toBeCloseTo(-100, 5);
  });

  it("fades out smoothly rather than stepping", () => {
    const pulled = pullStroke(ring, { x: 100, y: 0 }, { x: 40, y: 0 }, circumference / 4);
    const moved = (i: number) => pulled[i]!.x - ring[i]!.x;
    expect(moved(0)).toBeGreaterThan(moved(3));
    expect(moved(3)).toBeGreaterThan(moved(6));
    expect(moved(6)).toBeGreaterThan(0);
    // A quarter of the way round, measured along the chords: as good as still.
    expect(Math.abs(moved(9))).toBeLessThan(0.01);
  });

  it("goes the short way round a ring", () => {
    // The last point is next to the first along the ring, not a full turn away.
    const pulled = pullStroke(ring, { x: 100, y: 0 }, { x: 40, y: 0 }, circumference / 4);
    expect(pulled[35]!.x - ring[35]!.x).toBeGreaterThan(30);
  });

  it("leaves an open line's far end alone", () => {
    const line: Point[] = Array.from({ length: 11 }, (_, i) => ({ x: i * 10, y: 0 }));
    const pulled = pullStroke(line, { x: 0, y: 0 }, { x: 0, y: 20 }, 25);
    expect(pulled[0]!.y).toBeCloseTo(20, 5);
    expect(pulled[10]!.y).toBe(0);
  });
});

describe("the reach of a ring", () => {
  it("is measured to its outline in each direction", () => {
    const box: Point[] = [
      { x: -200, y: -100 },
      { x: 200, y: -100 },
      { x: 200, y: 100 },
      { x: -200, y: 100 },
    ];
    const reach = rimReach(box, { x: 0, y: 0 });
    expect(reach(0)).toBeCloseTo(200, 5);
    expect(reach(180)).toBeCloseTo(200, 5);
    expect(reach(-90)).toBeCloseTo(100, 5);
    expect(reach(90)).toBeCloseTo(100, 5);
  });
});

describe("keeping remarks in one margin", () => {
  const label = { width: 100, height: 40 };

  it("follows the last remark's direction even when something nearer is free", () => {
    // Out to the right is blocked close in, but clear a little further out.
    // Straight down is free immediately -- and should still lose, because the
    // previous remark went right and notes belong in one margin. The sliver
    // sits just under the leader's line, so the words hit it and the line
    // does not.
    const sliver: Rect = { x: 105, y: 10, width: 30, height: 50 };
    const at = clearSpot({ x: 0, y: 0 }, 100, 10, label, [sliver], 5, 0);
    expect(at.x).toBeGreaterThan(0);
    expect(Math.abs(at.y)).toBeLessThan(1);
  });

  it("falls back to the compass when the margin is full", () => {
    const wall: Rect = { x: 50, y: -500, width: 2000, height: 1000 };
    const at = clearSpot({ x: 0, y: 0 }, 100, 10, label, [wall], 5, 0);
    expect(at.x).toBeLessThanOrEqual(0);
  });
});

describe("the shape around a remark", () => {
  const marks: Point[] = [
    { x: 0, y: 0 },
    { x: 100, y: 0 },
    { x: 100, y: 60 },
    { x: 0, y: 60 },
  ];

  it("clears what it contains rather than cutting its corners off", () => {
    const blob = blobAround(marks, 20);
    for (const m of marks) {
      // Every mark is strictly inside the shape drawn around it.
      expect(insidePolygon(m, blob)).toBe(true);
    }
  });

  it("draws as a closed rounded path", () => {
    const d = smoothClosedPath(blobAround(marks, 20));
    expect(d.startsWith("M ")).toBe(true);
    expect(d.endsWith(" Z")).toBe(true);
    expect(d).toContain("Q");
  });

  it("says nothing about a shape with no area", () => {
    expect(smoothClosedPath([{ x: 1, y: 1 }])).toBe("");
  });
});

describe("calling out highlights down the sides of a card", () => {
  const node: Rect = { x: 0, y: 0, width: 200, height: 300 };

  it("sends each highlight out by its nearest edge", () => {
    const places = calloutPlaces(
      [
        { id: "l", centre: { x: 40, y: 150 } },
        { id: "r", centre: { x: 160, y: 150 } },
      ],
      node,
      20,
    );
    expect(places.get("l")!.side).toBe("left");
    expect(places.get("l")!.x).toBe(-20);
    expect(places.get("r")!.side).toBe("right");
    expect(places.get("r")!.x).toBe(220);
  });

  it("spreads them over the card's height instead of stacking them", () => {
    const places = calloutPlaces(
      [
        { id: "a", centre: { x: 160, y: 100 } },
        { id: "b", centre: { x: 160, y: 110 } },
        { id: "c", centre: { x: 160, y: 120 } },
      ],
      node,
      20,
    );
    expect([...places.values()].map((p) => p.y)).toEqual([75, 150, 225]);
  });

  it("keeps them in the order their highlights are in, so leaders do not cross", () => {
    const places = calloutPlaces(
      [
        { id: "low", centre: { x: 160, y: 280 } },
        { id: "high", centre: { x: 160, y: 20 } },
      ],
      node,
      20,
    );
    expect(places.get("high")!.y).toBeLessThan(places.get("low")!.y);
  });

  it("gives the same answer whatever order they were drawn in", () => {
    const a: Callout[] = [
      { id: "1", centre: { x: 160, y: 50 } },
      { id: "2", centre: { x: 160, y: 250 } },
    ];
    const one = calloutPlaces(a, node, 20);
    const other = calloutPlaces([...a].reverse(), node, 20);
    expect(one.get("1")).toEqual(other.get("1"));
    expect(one.get("2")).toEqual(other.get("2"));
  });

  it("counts each side on its own", () => {
    const places = calloutPlaces(
      [
        { id: "l", centre: { x: 10, y: 150 } },
        { id: "r", centre: { x: 190, y: 150 } },
      ],
      node,
      20,
    );
    // One on each side: each sits at the card's middle, not at a third of it.
    expect(places.get("l")!.y).toBe(150);
    expect(places.get("r")!.y).toBe(150);
  });
});
