/**
 * strikes.ts  -  a cross drawn over an edge, read as "take this link away".
 *
 * Two strokes crossing each other on top of a line between cards is the
 * plainest editing mark there is, and the queue could not carry it: the
 * strokes caught no card, so the intent arrived as two short lines on empty
 * canvas and a hope. The browser knows where every edge is drawn, so the
 * cross is read here and travels as the edge it struck out, by id and by
 * its two ends -- something an agent can act on without a picture.
 */

import { isLoop, type Point } from "./lasso";

/** An edge as drawn on screen, in the same coordinates as the strokes. */
export type EdgePath = { id: string; source: string; target: string; points: Point[] };

export type Strike = {
  /** The edge the cross was drawn over. */
  edge: string;
  source: string;
  target: string;
  /** Where the two strokes crossed, in canvas coordinates. */
  x: number;
  y: number;
};

/**
 * How near to the edge the crossing has to be.
 *
 * A cross aimed at a thin line by hand lands beside it as often as on it.
 */
export const STRIKE_PX = 24;

/**
 * How far along each stroke the crossing may sit and still be a cross.
 *
 * A cross meets in the middle of both strokes. Two strokes meeting near
 * their ends are a corner or a tick, not a cross, and one crossing the
 * other's tip is a stroke that happened to touch.
 */
const MID = 0.2;

function crossing(a: Point[], b: Point[]): { at: Point; fa: number; fb: number } | null {
  const la = lengths(a);
  const lb = lengths(b);
  for (let i = 1; i < a.length; i++) {
    for (let j = 1; j < b.length; j++) {
      const hit = segmentPoint(a[i - 1]!, a[i]!, b[j - 1]!, b[j]!);
      if (!hit) continue;
      const fa = (la[i - 1]! + dist(a[i - 1]!, hit.at)) / la[la.length - 1]!;
      const fb = (lb[j - 1]! + dist(b[j - 1]!, hit.at)) / lb[lb.length - 1]!;
      return { at: hit.at, fa, fb };
    }
  }
  return null;
}

function lengths(s: Point[]): number[] {
  const out = [0];
  for (let i = 1; i < s.length; i++) out.push(out[i - 1]! + dist(s[i - 1]!, s[i]!));
  return out;
}

function dist(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function segmentPoint(p1: Point, p2: Point, p3: Point, p4: Point): { at: Point } | null {
  const d = (p2.x - p1.x) * (p4.y - p3.y) - (p2.y - p1.y) * (p4.x - p3.x);
  if (d === 0) return null;
  const t = ((p3.x - p1.x) * (p4.y - p3.y) - (p3.y - p1.y) * (p4.x - p3.x)) / d;
  const u = ((p3.x - p1.x) * (p2.y - p1.y) - (p3.y - p1.y) * (p2.x - p1.x)) / d;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return { at: { x: p1.x + t * (p2.x - p1.x), y: p1.y + t * (p2.y - p1.y) } };
}

/** Distance from a point to the nearest piece of a polyline. */
function distanceToPath(p: Point, path: Point[]): number {
  let best = Infinity;
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1]!;
    const b = path[i]!;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len2 = dx * dx + dy * dy;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2));
    best = Math.min(best, dist(p, { x: a.x + t * dx, y: a.y + t * dy }));
  }
  return best;
}

/**
 * The edges struck out by a set of strokes.
 *
 * A strike is two open strokes that cross each other near their middles,
 * with the crossing on or beside an edge. The nearest edge wins when the
 * cross sits where two run close together. Each edge is struck at most
 * once, however many times it was crossed.
 */
export function resolveStrikes(strokes: Point[][], edges: EdgePath[]): Strike[] {
  const strikes: Strike[] = [];
  const open = strokes.filter((s) => s.length >= 2 && !isLoop(s));
  for (let i = 0; i < open.length; i++) {
    for (let j = i + 1; j < open.length; j++) {
      const x = crossing(open[i]!, open[j]!);
      if (!x) continue;
      if (x.fa < MID || x.fa > 1 - MID || x.fb < MID || x.fb > 1 - MID) continue;
      let best: { edge: EdgePath; d: number } | null = null;
      for (const edge of edges) {
        if (edge.points.length < 2) continue;
        const d = distanceToPath(x.at, edge.points);
        if (d <= STRIKE_PX && (best === null || d < best.d)) best = { edge, d };
      }
      if (!best || strikes.some((s) => s.edge === best!.edge.id)) continue;
      strikes.push({
        edge: best.edge.id,
        source: best.edge.source,
        target: best.edge.target,
        x: x.at.x,
        y: x.at.y,
      });
    }
  }
  return strikes;
}

/** The strikes as a sentence, for a reader who only gets text. */
export function describeStrikes(strikes: Strike[]): string {
  return strikes
    .map((s) => `strike out edge ${s.edge} (${s.source} -> ${s.target})`)
    .join("; ");
}
