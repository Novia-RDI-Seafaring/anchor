/**
 * cuts.ts — a line drawn across a table, read as "between these two rows".
 *
 * "Split here" with a line through a table is the most natural editing
 * gesture there is, and until now it was the one the queue could not carry.
 * A ring resolves to a node; a line between shapes resolves to an edge; but
 * a single line across a card resolved to the card and nothing more -- the
 * one thing the line said, WHERE, was dropped. Five intents in a row arrived
 * as "split here" plus a card id, and each needed a screenshot to act on.
 *
 * The browser knows where every row sits on screen. So the cut is worked out
 * here, where that knowledge lives, and travels as a row boundary an agent
 * can act on without seeing anything: `after: "B"`.
 */

import { isLoop, type Box, type Point } from "@/canvas/lasso";

/** One row's vertical extent, in the same coordinates as the strokes. */
export type RowBand = { key: string; top: number; bottom: number };

export type Cut = {
  /** The card the line crosses. */
  node: string;
  /** The row above the cut, by its key. */
  after: string;
  /** The same row by position, for a reader that wants an index. */
  afterIndex: number;
  /** Where the line crossed the card, in canvas coordinates. */
  y: number;
};

/**
 * How level a line has to be, height over width, to count as a cut.
 *
 * A cut runs across; a stroke that drops as far as it travels is pointing at
 * something, not dividing it. Generous, because a hand drawing a horizontal
 * line rarely manages one.
 */
const LEVEL_RATIO = 0.6;

/**
 * Where a stroke crosses a card's vertical centre line, or null if it never
 * reaches that far. A line that only clips a corner has not crossed the card.
 */
function crossingY(stroke: Point[], box: Box): number | null {
  const mid = box.x + box.width / 2;
  for (let i = 1; i < stroke.length; i++) {
    const a = stroke[i - 1]!;
    const b = stroke[i]!;
    if ((a.x - mid) * (b.x - mid) > 0) continue;
    if (a.x === b.x) return a.y;
    const t = (mid - a.x) / (b.x - a.x);
    const y = a.y + t * (b.y - a.y);
    if (y >= box.y && y <= box.y + box.height) return y;
  }
  return null;
}

/**
 * The cuts a set of strokes make, given each card's rows.
 *
 * Only a level, open stroke that crosses a card between two of its rows
 * counts. The boundary nearest to where it crossed wins, so a line drawn a
 * little into row C still reads as "after B" -- the hand aims at the gap and
 * lands near it. A line above the first row or below the last divides
 * nothing and is left alone rather than invented into a cut.
 */
export function resolveCuts(
  strokes: Point[][],
  boxes: Box[],
  rowsOf: (nodeId: string) => RowBand[] | null,
): Cut[] {
  const cuts: Cut[] = [];
  for (const stroke of strokes) {
    if (stroke.length < 2 || isLoop(stroke)) continue;
    const xs = stroke.map((p) => p.x);
    const ys = stroke.map((p) => p.y);
    const width = Math.max(...xs) - Math.min(...xs);
    const height = Math.max(...ys) - Math.min(...ys);
    if (width === 0 || height / width > LEVEL_RATIO) continue;
    for (const box of boxes) {
      const y = crossingY(stroke, box);
      if (y === null) continue;
      const rows = rowsOf(box.id);
      if (!rows || rows.length < 2) continue;
      // Boundaries between consecutive rows; the nearest one to the crossing.
      let best: { index: number; distance: number } | null = null;
      for (let i = 0; i < rows.length - 1; i++) {
        const boundary = (rows[i]!.bottom + rows[i + 1]!.top) / 2;
        const distance = Math.abs(y - boundary);
        if (best === null || distance < best.distance) best = { index: i, distance };
      }
      if (best === null) continue;
      // Above the first row or below the last: not between anything.
      if (y < rows[0]!.top || y > rows[rows.length - 1]!.bottom) continue;
      const row = rows[best.index]!;
      if (cuts.some((c) => c.node === box.id && c.after === row.key)) continue;
      cuts.push({ node: box.id, after: row.key, afterIndex: best.index, y });
    }
  }
  return cuts;
}

/** The cuts as a sentence, for a reader who only gets text. */
export function describeCuts(cuts: Cut[]): string {
  return cuts.map((c) => `cut ${c.node} after row ${c.after}`).join("; ");
}
