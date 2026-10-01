/**
 * lasso.ts — turning a stroke into the things it is about.
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
function extent(points: Point[]): number {
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

/**
 * A stroke that rings something and then heads off, split into the two.
 *
 * One gesture, two jobs: the loop says what this is about, the tail says
 * where the words go. They should not move together -- swinging the whole
 * stroke to follow a label drags the ring off the thing it was drawn around,
 * which is the one part that must not move.
 *
 * The loop is the longest opening run that comes back to where it started.
 * Taking the LAST such return rather than the first matters: a scribbled ring
 * often crosses its own start early, and cutting there would leave most of
 * the ring in the tail.
 */
export function loopAndTail(points: Point[]): { loop: Point[]; tail: Point[] } | null {
  if (points.length < 6) return null;
  const start = points[0]!;
  let close = -1;
  for (let i = 3; i < points.length; i++) {
    const run = points.slice(0, i + 1);
    const span = Math.max(extent(run), MIN_STROKE_PX);
    if (Math.hypot(points[i]!.x - start.x, points[i]!.y - start.y) <= span * LOOP_CLOSE_RATIO) {
      close = i;
    }
  }
  // No return, or it returned only at the very end: a ring with no tail.
  if (close < 3 || close >= points.length - 2) return null;
  return { loop: points.slice(0, close + 1), tail: points.slice(close) };
}

/**
 * The middle of the eye: what the tail swings about.
 *
 * The area's centre, not the average of the points. A hand-drawn ring is
 * sampled unevenly -- dense where the hand slowed, sparse where it swept --
 * and averaging vertices drags the centre toward the crowded side. A closing
 * point that lands back on the opening one does the same thing on its own.
 * The area does not care how the outline was sampled.
 */
export function loopCentre(loop: Point[]): Point {
  let twiceArea = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < loop.length; i++) {
    const a = loop[i]!;
    const b = loop[(i + 1) % loop.length]!;
    const cross = a.x * b.y - b.x * a.y;
    twiceArea += cross;
    cx += (a.x + b.x) * cross;
    cy += (a.y + b.y) * cross;
  }
  // A ring with no enclosed area -- a there-and-back scribble -- has no
  // centre to speak of, so fall back to the middle of its points.
  if (Math.abs(twiceArea) < 1e-9) {
    const n = loop.length || 1;
    return {
      x: loop.reduce((acc, p) => acc + p.x, 0) / n,
      y: loop.reduce((acc, p) => acc + p.y, 0) / n,
    };
  }
  return { x: cx / (3 * twiceArea), y: cy / (3 * twiceArea) };
}

/** Where a ray out of `from` leaves the loop, or `from` if it never enters it. */
export function exitLoop(loop: Point[], from: Point, to: Point): Point {
  let best: Point | null = null;
  let far = -1;
  for (let i = 0; i < loop.length; i++) {
    const a = loop[i]!;
    const b = loop[(i + 1) % loop.length]!;
    const hit = segmentPoint(from, to, a, b);
    if (!hit) continue;
    const d = Math.hypot(hit.x - from.x, hit.y - from.y);
    // The LAST crossing: a wobbly ring can be met more than once, and the
    // line should start outside all of it.
    if (d > far) {
      far = d;
      best = hit;
    }
  }
  return best ?? from;
}

/** Where two segments meet, or null. */
function segmentPoint(p1: Point, p2: Point, p3: Point, p4: Point): Point | null {
  const d = (p2.x - p1.x) * (p4.y - p3.y) - (p2.y - p1.y) * (p4.x - p3.x);
  if (d === 0) return null;
  const t = ((p3.x - p1.x) * (p4.y - p3.y) - (p3.y - p1.y) * (p4.x - p3.x)) / d;
  const u = ((p3.x - p1.x) * (p2.y - p1.y) - (p3.y - p1.y) * (p2.x - p1.x)) / d;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return { x: p1.x + t * (p2.x - p1.x), y: p1.y + t * (p2.y - p1.y) };
}

/**
 * The outline of a ring: its convex hull, in order.
 *
 * What a reader sees when they ring something is the area enclosed, not the
 * exact path of the pen. Those differ whenever the hand dents inward -- a
 * sharp corner cut into a box, a loop that crosses back through itself -- and
 * the dent is the reader's wobble, not a place they meant to put anything.
 *
 * Clipping a line against the literal ink lets it begin inside one of those
 * dents, so it appears to start within the shape and bend its way out. The
 * hull has no dents, so a line clipped against it always leaves from the
 * outline the reader can actually see.
 */
export function ringOutline(points: Point[]): Point[] {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  if (sorted.length < 3) return sorted;
  const half = (input: Point[]): Point[] => {
    const out: Point[] = [];
    for (const p of input) {
      while (out.length >= 2 && cross(out[out.length - 2]!, out[out.length - 1]!, p) <= 0) {
        out.pop();
      }
      out.push(p);
    }
    out.pop();
    return out;
  };
  return [...half(sorted), ...half([...sorted].reverse())];
}

/** Which way the corner at b turns, going a -> b -> c. */
function cross(a: Point, b: Point, c: Point): number {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

/**
 * The part of a tail that is actually outside the ring, starting on its edge.
 *
 * One gesture -- ring a thing, carry on out to where the words go -- is two
 * marks: an encirclement, and a line leaving it. Cutting them apart at the
 * moment they are drawn is what keeps them independent afterwards, so the
 * ring can stay put while the line swings, with no surgery at drag time and
 * no stub of tail left curling inside the ring.
 */
export function lineOutOfLoop(loop: Point[], tail: Point[]): Point[] {
  // Against the outline, not the ink: a line must not start inside a dent.
  const outline = ringOutline(loop);
  if (outline.length < 3) return tail;
  const outside = tail.filter((p) => !pointInPolygon(p, outline));
  const first = outside[0];
  if (!first) return [];
  return [exitLoop(outline, loopCentre(outline), first), ...outside];
}

/**
 * The same stroke swung round its own start, so its far end lands on `to`.
 *
 * Rotation and an even scale together, which is what "pivot the line" means
 * when the line has a length as well as a direction: drag the far end further
 * out and the whole stroke lengthens, drag it round and the whole stroke
 * swings. The hand's wobble rides along instead of being straightened out,
 * because every point takes the same transform.
 *
 * Dragging a label at the end of a line should do this, rather than leaving
 * the line where it was and running a second line out to the words -- that
 * puts an elbow in the middle of one gesture.
 */
export function pivotStroke(stroke: Point[], to: Point): Point[] {
  const start = stroke[0];
  const end = stroke[stroke.length - 1];
  if (!start || !end || stroke.length < 2) return stroke;
  const was = { x: end.x - start.x, y: end.y - start.y };
  const now = { x: to.x - start.x, y: to.y - start.y };
  const wasLength = Math.hypot(was.x, was.y);
  // A stroke that started and ended in the same place has no direction to
  // swing; leave it be rather than dividing by nothing.
  if (wasLength === 0) return stroke;
  const scale = Math.hypot(now.x, now.y) / wasLength;
  const turn = Math.atan2(now.y, now.x) - Math.atan2(was.y, was.x);
  const cos = Math.cos(turn) * scale;
  const sin = Math.sin(turn) * scale;
  return stroke.map((p) => {
    const dx = p.x - start.x;
    const dy = p.y - start.y;
    return { x: start.x + dx * cos - dy * sin, y: start.y + dx * sin + dy * cos };
  });
}

/**
 * Where an open stroke was going when it stopped.
 *
 * A line drawn out to clear canvas is already a leader -- the reader drew it
 * to point somewhere. So the words carry on from its end, in the direction it
 * was travelling, and no second line is invented to lead to them.
 *
 * The direction is taken from a little way back rather than from the last two
 * points, which are a millisecond apart and mostly hand tremor.
 */
export function strokeHeading(stroke: Point[], lookBack = 24): { end: Point; from: Point } {
  const end = stroke[stroke.length - 1] ?? { x: 0, y: 0 };
  let i = stroke.length - 1;
  let travelled = 0;
  while (i > 0 && travelled < lookBack) {
    travelled += Math.hypot(stroke[i]!.x - stroke[i - 1]!.x, stroke[i]!.y - stroke[i - 1]!.y);
    i--;
  }
  return { end, from: stroke[i] ?? end };
}

export type Callout = { id: string; centre: Point };
export type CalloutPlace = { x: number; y: number; side: "left" | "right" };

/**
 * Where the words go for highlights drawn on one card: a margin down each
 * side, the way a drawing is called out.
 *
 * Which side is decided by the half of the card the highlight sits in, so the
 * words leave by the nearest edge and the leader never crosses the card. Down
 * each side they are spread evenly over the card's height, keeping the order
 * their highlights are in, so a leader never has to cross another one to
 * reach its own words.
 *
 * Spread, not stacked at their own heights: two highlights on adjacent rows
 * would put their words on top of each other, and nudging them apart one at a
 * time gives a different answer depending on which was drawn first. Dividing
 * the height between them is stable -- the same set of highlights always
 * lands the same way, however they were made -- which is what lets the
 * remaining words re-flow calmly when one is added or taken away.
 */
export function calloutPlaces(
  items: Callout[],
  node: Rect,
  gap: number,
): Map<string, CalloutPlace> {
  const middle = node.x + node.width / 2;
  const places = new Map<string, CalloutPlace>();
  for (const side of ["left", "right"] as const) {
    const mine = items
      .filter((i) => (i.centre.x < middle ? "left" : "right") === side)
      .sort((a, b) => a.centre.y - b.centre.y);
    mine.forEach((item, i) => {
      places.set(item.id, {
        x: side === "left" ? node.x - gap : node.x + node.width + gap,
        // Evenly through the height, inset from both ends rather than
        // starting hard against the top edge.
        y: node.y + ((i + 1) / (mine.length + 1)) * node.height,
        side,
      });
    });
  }
  return places;
}

/**
 * A soft shape around everything one remark covers.
 *
 * A remark is usually several marks and several notes scattered over a
 * card or two, and nothing on screen says which of them belong together --
 * least of all the button that files them, sitting off in a corner with no
 * visible connection to what it is about to send. Drawing one quiet shape
 * around the lot gives that button something to belong to.
 *
 * The outline is the hull pushed outward from the middle, so it clears what
 * it contains rather than cutting corners off it.
 */
export function blobAround(points: Point[], pad: number): Point[] {
  const hull = ringOutline(points);
  if (hull.length < 3) return hull;
  const centre = loopCentre(hull);
  return hull.map((p) => {
    const dx = p.x - centre.x;
    const dy = p.y - centre.y;
    const d = Math.hypot(dx, dy) || 1;
    return { x: p.x + (dx / d) * pad, y: p.y + (dy / d) * pad };
  });
}

/**
 * A closed polygon drawn as a rounded shape.
 *
 * Curves through the midpoint of every edge with the vertex as the control
 * point, which rounds every corner without needing to know where the corners
 * are. A hull is all corners, and a remark is not an angular thing.
 */
export function smoothClosedPath(points: Point[]): string {
  if (points.length < 3) return "";
  const mid = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  const start = mid(points[points.length - 1]!, points[0]!);
  let d = `M ${start.x} ${start.y}`;
  for (let i = 0; i < points.length; i++) {
    const here = points[i]!;
    const next = points[(i + 1) % points.length]!;
    const to = mid(here, next);
    d += ` Q ${here.x} ${here.y} ${to.x} ${to.y}`;
  }
  return `${d} Z`;
}

/**
 * Where to put words so they land on empty canvas.
 *
 * The words sit a short line out from the RIM of what they are about, not a
 * multiple of its size out from its middle. Measured from the middle, a ring
 * round two cards put its words as far away as the ring was wide -- an acre
 * off, on a leader nobody could follow -- while a small ring on one row got
 * them close in. The rim is what the reader sees the line leave, so it is
 * what the gap is measured from, and a big ring gets the same short leader
 * as a small one.
 *
 * Sides are tried first: a label to the left or right of a thing reads as
 * the thing's caption, the way words called out down a card's sides do,
 * while one above or below reads as a heading or a footnote. Then the
 * diagonals, then straight up, and straight down last because that is where
 * the page continues. Each direction is tried close in before further out,
 * so the words stay near what they are about.
 *
 * Everything already on the canvas counts as occupied -- cards, earlier ink,
 * earlier words -- because a remark written on top of another one is worse
 * than a remark written slightly further away.
 */
const COMPASS_DEGREES = [0, 180, -45, -135, 45, 135, -90, 90];

export function clearSpot(
  centre: Point,
  /**
   * How far the rim is from the centre, either one number for something
   * round or a function of the direction (in degrees) for a shape that is
   * not.
   */
  rim: number | ((deg: number) => number),
  /** The leader's length: how far past the rim the words start. */
  gap: number,
  label: { width: number; height: number },
  occupied: Rect[],
  pad: number,
  /**
   * Which way the last remark went, if there was one.
   *
   * Tried at every distance before any other direction is tried at all.
   * Notes on a page line up in a margin: a reader who put the last one out to
   * the right expects the next one out to the right too, and a nearer gap in
   * some other direction is not worth breaking that for. Without this, a
   * sliver of card overlapping the near position was enough to send one
   * remark down while its neighbour went sideways.
   */
  prefer?: number,
): Point {
  const reach = typeof rim === "number" ? () => rim : rim;
  let best: Point | null = null;
  let bestClash = Infinity;
  // Multiples of the leader, so further out still means a line the eye can
  // follow rather than a jump to the next clear acre.
  const steps = [1, 2.5, 4.5, 7];
  const order: [number, number][] = [
    ...(prefer === undefined ? [] : steps.map((st): [number, number] => [st, prefer])),
    ...steps.flatMap((st) => COMPASS_DEGREES.map((d): [number, number] => [st, d])),
  ];
  for (const [step, deg] of order) {
    const r = (deg * Math.PI) / 180;
    const edge = reach(deg);
    const distance = edge + gap * step;
    const at = {
      x: centre.x + Math.cos(r) * distance,
      y: centre.y + Math.sin(r) * distance,
    };
    // The line has to leave the rim on open canvas. A ring round two cards
    // has most of its rim over them, and a leader that set off from inside
    // one read as being about that card, not the ring. So the rim point and
    // the line out from it are checked too, not just where the words land.
    const from = { x: centre.x + Math.cos(r) * edge, y: centre.y + Math.sin(r) * edge };
    const leaderBlocked = [0, 1 / 3, 2 / 3].some((f) => {
      const q = { x: from.x + (at.x - from.x) * f, y: from.y + (at.y - from.y) * f };
      return occupied.some((o) => insideRect(q, o));
    });
    if (leaderBlocked) continue;
    // Where the words will actually sit, which is not centred on this
    // point: they run AWAY from the leader, rightward from it unless the
    // line went left, and they straddle it vertically because the line
    // meets the middle of the text. Judging a centred box instead made
    // every outward direction look half-blocked by whatever the line had
    // just left, and pushed the offer downward into open page.
    const box: Rect = {
      x: Math.cos(r) < 0 ? at.x - label.width : at.x,
      y: at.y - label.height / 2,
      width: label.width,
      height: label.height,
    };
    const clash = occupied.reduce((sum, o) => sum + overlapArea(box, grow(o, pad)), 0);
    if (clash === 0) return at;
    if (clash < bestClash) {
      bestClash = clash;
      best = at;
    }
  }
  // Nowhere is clear: the least cluttered of them, rather than nothing.
  return best ?? { x: centre.x + reach(0) + gap, y: centre.y };
}

/**
 * How far a ring's outline is from its centre in a given direction.
 *
 * A ring drawn by hand is nothing like round: one round two cards side by
 * side is twice as wide as it is tall. Measuring its reach by direction is
 * what lets a leader leave its rim by the same short distance whichever way
 * it goes.
 */
export function rimReach(outline: Point[], centre: Point): (deg: number) => number {
  const span = outline.reduce(
    (m, p) => Math.max(m, Math.hypot(p.x - centre.x, p.y - centre.y)),
    0,
  );
  return (deg) => {
    const r = (deg * Math.PI) / 180;
    // Aim well past the outline: the exit is the last crossing on the way.
    const far = { x: centre.x + Math.cos(r) * span * 4, y: centre.y + Math.sin(r) * span * 4 };
    const exit = exitLoop(outline, centre, far);
    return Math.hypot(exit.x - centre.x, exit.y - centre.y);
  };
}

function insideRect(p: Point, r: Rect): boolean {
  return p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height;
}

function grow(r: Rect, pad: number): Rect {
  return { x: r.x - pad, y: r.y - pad, width: r.width + pad * 2, height: r.height + pad * 2 };
}

function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

/**
 * How text should sit at the end of a leader, so it carries on the line.
 *
 * Words at the end of a line are the line still going: the eye follows the
 * stroke into them without a corner to turn. A horizontal field hanging off a
 * diagonal leader reads as two separate objects that happen to touch.
 *
 * `deg` is the angle to rotate the text by, always within a quarter turn of
 * upright, so it can lean hard but never goes upside down or reads backwards.
 * `flip` says the line ran leftward, so the words extend back from their right
 * edge instead of forward from their left -- which is what keeps them running
 * the same way the line was travelling while still reading left to right.
 */
export function leaderAngle(from: Point, to: Point): { deg: number; flip: boolean } {
  const deg = (Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI;
  // Leftward: turn the text back the right way up and hang it off its far
  // edge. Rotating by the raw angle would stand the words on their head.
  const flip = deg > 90 || deg < -90;
  // Turn back through the nearer half. Always subtracting would send a leader
  // pointing due left (-180) round a full turn instead of levelling it.
  return { deg: flip ? (deg > 0 ? deg - 180 : deg + 180) : deg, flip };
}

/**
 * A leader that lands level, so the words at its end read as a line of text.
 *
 * The last control point shares the label's height: that alone is what makes
 * the curve level as it lands, from the left into words that run right and
 * from the right into words that run left. How it departs is the caller's:
 * a highlight inside a card leaves sideways (`level`), the way a drawing's
 * callouts do; a ring's leader leaves along the line to the words (`chord`),
 * since a rim can be left in any direction.
 */
export function leaderPath(a: Point, b: Point, depart: "level" | "chord" = "chord"): string {
  const left = b.x < a.x;
  const reach = Math.min(90, Math.max(24, Math.abs(b.x - a.x) * 0.6));
  const c1 =
    depart === "level"
      ? { x: a.x + (b.x - a.x) * 0.35, y: a.y }
      : { x: a.x + (b.x - a.x) * 0.35, y: a.y + (b.y - a.y) * 0.35 };
  const c2 = { x: left ? b.x + reach : b.x - reach, y: b.y };
  return `M ${a.x} ${a.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${b.x} ${b.y}`;
}

/**
 * A stroke pulled at one place, the way a hand pulls on a rubber band.
 *
 * The point nearest the grab moves the whole way; points along the line
 * from it move less, falling off smoothly to nothing at `reach` (measured
 * along the line, and the short way round for a ring). A ring drawn one row
 * short is fixed by pulling its edge over the row, without redrawing it and
 * without any of the shape's forty points being shown or picked.
 */
export function pullStroke(points: Point[], grab: Point, delta: Point, reach: number): Point[] {
  if (points.length < 2 || reach <= 0) return points;
  // Arc position of every point, and the total length.
  const at: number[] = [0];
  for (let i = 1; i < points.length; i++) {
    at.push(at[i - 1]! + Math.hypot(points[i]!.x - points[i - 1]!.x, points[i]!.y - points[i - 1]!.y));
  }
  const total = at[at.length - 1]!;
  if (total === 0) return points;
  let nearest = 0;
  let best = Infinity;
  for (let i = 0; i < points.length; i++) {
    const d = Math.hypot(points[i]!.x - grab.x, points[i]!.y - grab.y);
    if (d < best) {
      best = d;
      nearest = i;
    }
  }
  const ring = isLoop(points);
  const from = at[nearest]!;
  return points.map((p, i) => {
    let d = Math.abs(at[i]! - from);
    if (ring) d = Math.min(d, total - d);
    if (d >= reach) return p;
    const t = 1 - d / reach;
    const w = t * t * (3 - 2 * t);
    return { x: p.x + delta.x * w, y: p.y + delta.y * w };
  });
}

/** Add or remove one id, for correcting a proposal by hand. */
export function toggleId(ids: readonly string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((v) => v !== id) : [...ids, id];
}
