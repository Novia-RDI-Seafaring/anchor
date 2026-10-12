import { extent, MIN_STROKE_PX, LOOP_CLOSE_RATIO, insidePolygon as pointInPolygon, type Point } from "./strokeGeometry";

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
