import {
  rectsOverlap,
  strokeBounds,
  type Point,
  type Rect
} from "@/canvas/lasso";
import { type Note, type Selection } from "@/stores/markupStore";
import { NOTE_FONT_PX, NOTE_H, NOTE_W } from "./constants";


/**
 * Roughly where a comment written on open canvas sits.
 *
 * Its anchor is the first line of text, and the words run down and away from
 * there; which way depends on the leader that brought them. Approximate on
 * purpose -- this decides which note the reader meant, not where a pixel goes.
 */
export function noteRect(n: Note): Rect {
  return {
    x: n.x - NOTE_W / 2,
    y: n.y - NOTE_FONT_PX,
    width: NOTE_W * 1.5,
    height: NOTE_H + NOTE_FONT_PX,
  };
}

/**
 * Everything on the mark-up layer the rubber band touches.
 *
 * Touch, not contain: a band that has to swallow a mark whole punishes the
 * reader for a short drag over a long stroke, and the selection is meant to be
 * corrected anyway.
 */
export function withinBand(band: Rect, strokes: Point[][], notes: Note[]): Selection {
  return {
    strokes: strokes
      .map((st, i) => [i, strokeBounds(st)] as const)
      .filter(([, b]) => rectsOverlap(band, b))
      .map(([i]) => i),
    notes: notes
      .filter((n) => n.inStroke === undefined && rectsOverlap(band, noteRect(n)))
      .map((n) => n.id),
  };
}

/** Is this point on a comment written on open canvas? */
export function hitsNote(p: Point, n: Note): boolean {
  if (n.inStroke !== undefined) return false;
  const r = noteRect(n);
  return p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height;
}

/**
 * All four corners of a box. Two opposite corners are enough to describe a
 * rectangle but not to bound one: a hull given only those can run straight
 * across the other two, which cut the corner off the very card a remark was
 * about.
 */
export function rectCorners(r: Rect): Point[] {
  return [
    { x: r.x, y: r.y },
    { x: r.x + r.width, y: r.y },
    { x: r.x + r.width, y: r.y + r.height },
    { x: r.x, y: r.y + r.height },
  ];
}
