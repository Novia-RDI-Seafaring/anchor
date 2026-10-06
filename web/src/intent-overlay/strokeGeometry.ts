/**
 * lasso.ts  -  turning a stroke into the things it is about.
 *
 * A reviewer marking up a canvas draws the way a teacher marks an essay:
 * rings round what is wrong, lines under what matters. On paper that gesture
 * is nearly useless to a machine, because the ring encloses pixels. Here it is
 * not, because every node has an id and a box -- so the stroke can be resolved
 * to a set of ids before anything downstream ever sees it, and what an agent
 * receives is "these three nodes" rather than a polyline.
 *
 * Every stroke proposes a selection. The shape only decides how generous the
 * proposal is:
 *
 *   a closed-ish loop  -> everything the enclosed AREA touches
 *   an open stroke     -> everything the stroke itself crosses
 *
 * One rule, two generosities, and no cliff between them: a ring drawn sloppily
 * degrades into the open-stroke rule instead of selecting nothing, and an
 * underline still gives you the card you underlined -- which is the gesture a
 * reviewer reaches for most.
 *
 * Generous on purpose. The proposal is meant to be corrected by hand, so a
 * near miss that includes one node too many costs a click, while a near miss
 * that includes nothing leaves the reader wondering what they did wrong.
 */

export type Point = { x: number; y: number };
export type Box = { id: string; x: number; y: number; width: number; height: number };

/**
 * How close the ends must come, relative to the stroke's own size, before it
 * counts as a loop. Proportional rather than absolute so the same gesture
 * reads the same whether it rings one cell or a whole column.
 */
export const LOOP_CLOSE_RATIO = 0.35;
/** Below this the stroke is a tap, not a gesture. */
export const MIN_STROKE_PX = 6;

/** Total length of the path, used to tell a tap from a stroke. */
export function strokeLength(points: Point[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    total += Math.hypot(points[i]!.x - points[i - 1]!.x, points[i]!.y - points[i - 1]!.y);
  }
  return total;
}

/**
 * Is this stroke closed enough to read as a ring?
 *
 * The gap between the ends is compared against the stroke's own extent, so a
 * small tight circle and a big loose one are judged by the same standard. A
 * stroke that doubles back on itself without travelling anywhere is not a
 * loop, however close its ends are -- hence the length floor.
 */
export function isLoop(points: Point[]): boolean {
  if (points.length < 4) return false;
  const length = strokeLength(points);
  if (length < MIN_STROKE_PX * 3) return false;
  const a = points[0]!;
  const b = points[points.length - 1]!;
  const span = Math.max(extent(points), MIN_STROKE_PX);
  return Math.hypot(b.x - a.x, b.y - a.y) <= span * LOOP_CLOSE_RATIO;
}

/** The larger side of the stroke's bounding box. */
export function extent(points: Point[]): number {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  return Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
}

/**
 * The ids a stroke proposes.
 *
 * A loop takes anything its enclosed area touches -- a node half inside the
 * ring counts, because a reviewer who drew around something meant it even if
 * the pen clipped a corner. An open stroke takes what it crosses.
 */
export function lassoHits(points: Point[], boxes: Box[]): string[] {
  if (points.length < 2 || strokeLength(points) < MIN_STROKE_PX) return [];
  const loop = isLoop(points);
  return boxes
    .filter((box) => (loop ? areaTouches(points, box) : strokeCrosses(points, box)))
    .map((box) => box.id);
}

/** Does the closed area overlap this box at all? */
function areaTouches(points: Point[], box: Box): boolean {
  // Cheapest first: a corner inside the ring, or the ring passing through.
  for (const corner of corners(box)) {
    if (pointInPolygon(corner, points)) return true;
  }
  if (strokeCrosses(points, box)) return true;
  // A card sitting wholly inside the ring has its centre inside it, whatever
  // its corners do -- a cheap test that does not depend on the card's
  // measured size being right.
  if (pointInPolygon({ x: box.x + box.width / 2, y: box.y + box.height / 2 }, points)) {
    return true;
  }
  // A ring drawn entirely inside a large node still points at that node.
  return pointInBox(points[0]!, box);
}

/** Does the stroke itself pass through this box? */
function strokeCrosses(points: Point[], box: Box): boolean {
  for (const p of points) if (pointInBox(p, box)) return true;
  for (let i = 1; i < points.length; i++) {
    if (segmentCrossesBox(points[i - 1]!, points[i]!, box)) return true;
  }
  return false;
}

function corners(box: Box): Point[] {
  return [
    { x: box.x, y: box.y },
    { x: box.x + box.width, y: box.y },
    { x: box.x + box.width, y: box.y + box.height },
    { x: box.x, y: box.y + box.height },
  ];
}

function pointInBox(p: Point, box: Box): boolean {
  return (
    p.x >= box.x && p.x <= box.x + box.width && p.y >= box.y && p.y <= box.y + box.height
  );
}

/** Ray casting. The polygon is the stroke, treated as closed. */
function pointInPolygon(p: Point, poly: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i]!;
    const b = poly[j]!;
    const straddles = a.y > p.y !== b.y > p.y;
    if (straddles && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) {
      inside = !inside;
    }
  }
  return inside;
}

function segmentCrossesBox(a: Point, b: Point, box: Box): boolean {
  const { x, y, width: w, height: h } = box;
  return (
    segmentsCross(a, b, { x, y }, { x: x + w, y }) ||
    segmentsCross(a, b, { x: x + w, y }, { x: x + w, y: y + h }) ||
    segmentsCross(a, b, { x: x + w, y: y + h }, { x, y: y + h }) ||
    segmentsCross(a, b, { x, y: y + h }, { x, y })
  );
}

function segmentsCross(p1: Point, p2: Point, p3: Point, p4: Point): boolean {
  const d = (p2.x - p1.x) * (p4.y - p3.y) - (p2.y - p1.y) * (p4.x - p3.x);
  if (d === 0) return false;
  const t = ((p3.x - p1.x) * (p4.y - p3.y) - (p3.y - p1.y) * (p4.x - p3.x)) / d;
  const u = ((p3.x - p1.x) * (p2.y - p1.y) - (p3.y - p1.y) * (p2.x - p1.x)) / d;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1;
}

/**
 * What a whole mark is about, across every stroke in it.
 *
 * A reviewer does not stop at one stroke: ring the value, draw a line across
 * to a clear patch, write the comment there. If every stroke selected, that
 * connecting line would sweep up whatever it happened to cross on the way,
 * and the mark would claim to be about cards the reviewer never looked at.
 *
 * So: rings always select, and the FIRST stroke selects whatever its shape.
 * Ringing two things in turn picks up both. Underlining a card and then
 * writing still targets that card. A line drawn away to somewhere is a line,
 * which is what it looks like.
 */
export function markHits(strokes: Point[][], boxes: Box[]): string[] {
  const out: string[] = [];
  const add = (id: string) => {
    if (!out.includes(id)) out.push(id);
  };
  strokes.forEach((stroke, i) => {
    if (i === 0 || isLoop(stroke)) {
      for (const id of lassoHits(stroke, boxes)) add(id);
      return;
    }
    // A later line is usually a connector: out to where the words go, or
    // across to another shape. What it passes over on the way is not what
    // the remark is about -- but what it starts or ends on is. A line drawn
    // out of a picture to a box that says "dimensions" is about that
    // picture; ignoring every line after the first left it uncaught.
    if (stroke.length < 2 || strokeLength(stroke) < MIN_STROKE_PX) return;
    const ends = [stroke[0]!, stroke[stroke.length - 1]!];
    for (const box of boxes) {
      if (ends.some((p) => pointInBox(p, box))) add(box.id);
    }
  });
  return out;
}

/**
 * Is this point inside the area a closed stroke encloses?
 *
 * Asks first whether the stroke is closed enough to count as a ring, because
 * a reader's open squiggle encloses nothing however the maths falls out.
 */
export function insideStroke(p: Point, stroke: Point[]): boolean {
  return isLoop(stroke) && pointInPolygon(p, stroke);
}

/**
 * Is this point inside this polygon?
 *
 * For shapes the code built rather than shapes a hand drew -- an outline, a
 * blob -- where closure is a given and the loop test would only get in the
 * way.
 */
export function insidePolygon(p: Point, polygon: Point[]): boolean {
  return pointInPolygon(p, polygon);
}

/** The bounding box of a stroke, for writing inside a shape that was drawn. */
export function strokeBounds(stroke: Point[]): { x: number; y: number; width: number; height: number } {
  const xs = stroke.map((p) => p.x);
  const ys = stroke.map((p) => p.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y };
}

/** Nothing drawn may be shrunk smaller than this, in flow units. */
export const MIN_BOX_PX = 24;

/**
 * The same stroke, remapped into a new bounding box.
 *
 * A drawn box that has been written in is no longer only a drawing, and it has
 * to be able to change size: to grow when the words outrun it, and to be
 * pulled bigger or smaller by hand. Stretching the ink like a rubber sheet is
 * the honest way to do that -- every wobble stretches with it, so the shape
 * still looks drawn rather than snapping to a rectangle nobody made.
 *
 * A stroke with no extent in one direction keeps its position in that
 * direction: there is nothing to stretch, and multiplying by a zero span would
 * collapse the whole thing onto a point.
 */
export function fitStroke(stroke: Point[], box: Rect): Point[] {
  return remapStroke(stroke, strokeBounds(stroke), box);
}

/** A box in flow coordinates. */
export type Rect = { x: number; y: number; width: number; height: number };

/**
 * One point carried from one box into another, keeping its relative place.
 *
 * This is what resizing a GROUP needs and resizing a single shape does not:
 * every selected mark moves and scales by the same transform, so a stroke in
 * the corner of the selection stays in the corner, rather than each one being
 * stretched to fill the whole box.
 */
export function remapPoint(p: Point, from: Rect, to: Rect): Point {
  return {
    x: from.width > 0 ? to.x + ((p.x - from.x) / from.width) * to.width : to.x,
    y: from.height > 0 ? to.y + ((p.y - from.y) / from.height) * to.height : to.y,
  };
}

export function remapStroke(stroke: Point[], from: Rect, to: Rect): Point[] {
  return stroke.map((p) => remapPoint(p, from, to));
}

/** Every one of these boxes, as one box. Empty in, nothing out. */
export function unionRect(rects: Rect[]): Rect | null {
  if (rects.length === 0) return null;
  const x = Math.min(...rects.map((r) => r.x));
  const y = Math.min(...rects.map((r) => r.y));
  return {
    x,
    y,
    width: Math.max(...rects.map((r) => r.x + r.width)) - x,
    height: Math.max(...rects.map((r) => r.y + r.height)) - y,
  };
}

/** Do these two boxes touch at all? The test a rubber band needs. */
export function rectsOverlap(a: Rect, b: Rect): boolean {
  return (
    a.x <= b.x + b.width &&
    b.x <= a.x + a.width &&
    a.y <= b.y + b.height &&
    b.y <= a.y + a.height
  );
}

/** The box two dragged corners describe, whichever way the drag went. */
export function rectFrom(a: Point, b: Point): Rect {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(b.x - a.x),
    height: Math.abs(b.y - a.y),
  };
}

/** The same stroke somewhere else. */
export function translateStroke(stroke: Point[], dx: number, dy: number): Point[] {
  return stroke.map((p) => ({ x: p.x + dx, y: p.y + dy }));
}

/**
 * Which drawn stroke is under this point, if any, within `slack`.
 *
 * For picking a mark back up to remove it. The slack is the reader's aim, not
 * the ink's width: a hairline is impossible to hit exactly and nobody should
 * have to try.
 */
export function strokeAt(p: Point, strokes: Point[][], slack: number): number {
  for (let i = strokes.length - 1; i >= 0; i--) {
    const stroke = strokes[i]!;
    for (let j = 1; j < stroke.length; j++) {
      if (pointToSegment(p, stroke[j - 1]!, stroke[j]!) <= slack) return i;
    }
  }
  return -1;
}

function pointToSegment(p: Point, a: Point, b: Point): number {
  const c = closestOnSegment(p, a, b);
  return Math.hypot(p.x - c.x, p.y - c.y);
}

function closestOnSegment(p: Point, a: Point, b: Point): Point {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return a;
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return { x: a.x + t * dx, y: a.y + t * dy };
}

/**
 * The point on a stroke nearest to somewhere else.
 *
 * Hand-drawn ink does not pass through the corners of its own bounding box: a
 * ring touches that box at four points and misses the corners by a wide
 * margin. So anything hung off the box -- a leader line, a button to erase the
 * stroke -- floats in empty canvas beside the mark rather than on it, and the
 * reader has to cross a gap to reach something that looks detached.
 *
 * Pulling the attachment back onto the nearest actual point of the path is
 * what "connected" means to the person who drew it. Aim at the corner, land on
 * the ink.
 */
export function nearestOnStroke(stroke: Point[], target: Point): Point {
  if (stroke.length === 0) return target;
  let best = stroke[0]!;
  let bestDistance = Infinity;
  for (let i = 1; i < stroke.length; i++) {
    const candidate = closestOnSegment(target, stroke[i - 1]!, stroke[i]!);
    const d = Math.hypot(candidate.x - target.x, candidate.y - target.y);
    if (d < bestDistance) {
      bestDistance = d;
      best = candidate;
    }
  }
  return best;
}

/**
 * How text should sit at the end of a leader: flowing away from where the
 * line came from, never back over it.
 *
 * Dragging left means the words extend leftward, so they hang from their
 * right edge. Dragging up means they grow upward, so they sit on their
 * bottom. The line's direction is the reader's own statement about which way
 * they wanted room.
 */
export function flowAway(
  from: Point,
  to: Point,
): { align: "left" | "right"; vAlign: "top" | "bottom" } {
  return {
    align: to.x < from.x ? "right" : "left",
    vAlign: to.y < from.y ? "bottom" : "top",
  };
}

/** Is this point inside the box, allowing `slack` beyond its edge? */
export function nearRect(p: Point, box: Rect, slack = 0): boolean {
  return (
    p.x >= box.x - slack &&
    p.x <= box.x + box.width + slack &&
    p.y >= box.y - slack &&
    p.y <= box.y + box.height + slack
  );
}

/**
 * The box a line has been dropped onto, if any.
 *
 * Near counts, not just over: a hand aiming at a card stops a few pixels short
 * as often as it stops a few pixels in, and the reader meant the same thing
 * both times. Only the END of the stroke is asked about -- a line that merely
 * crosses a card on its way past is travelling, not arriving.
 *
 * The smallest box wins where they overlap, since a card nested inside a
 * region is the more specific thing to have meant.
 */
export function dropTarget(stroke: Point[], boxes: Box[], slack: number): Box | null {
  const end = stroke[stroke.length - 1];
  if (!end) return null;
  return (
    boxes
      .filter((b) => nearRect(end, b, slack))
      .sort((a, b) => a.width * a.height - b.width * b.height)[0] ?? null
  );
}

/**
 * The stroke with its tail trimmed to where it first met the box.
 *
 * A connector that carries on into the middle of a card reads as a line drawn
 * over it; one that stops at the edge reads as a line joined to it. The point
 * of contact is found by halving the crossing segment, which is exact enough
 * for ink and needs no special case for which edge was met.
 */
export function clipToBox(points: Point[], box: Rect): Point[] {
  let i = points.length - 1;
  while (i >= 0 && nearRect(points[i]!, box)) i--;
  // Never reached the box, or never left it: nothing to trim.
  if (i < 0 || i === points.length - 1) return points;
  let outside = points[i]!;
  let inside = points[i + 1]!;
  for (let step = 0; step < 24; step++) {
    const mid = { x: (outside.x + inside.x) / 2, y: (outside.y + inside.y) / 2 };
    if (nearRect(mid, box)) inside = mid;
    else outside = mid;
  }
  return [...points.slice(0, i + 1), inside];
}
