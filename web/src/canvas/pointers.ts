/**
 * pointers.ts — a label drawn out of a card, read as "this, here".
 *
 * A line from one cell of a table out to some words is the plainest way to
 * say "this value". The line resolved to the card and nothing more, so "add
 * +1" arrived as a card id and the agent had to guess the row. The browser
 * knows where the line starts and where every row sits, so the row is worked
 * out here and travels with the words: `{node, row: "A"}`.
 */

import { type Box, type Point } from "@/canvas/lasso";
import { type RowBand } from "@/canvas/cuts";

export type Pointer = {
  /** The words the line leads to. */
  text: string;
  /** The card the line starts on. */
  node: string;
  /** The row it starts in, by its key, when the card has rows. */
  row?: string;
  /** The same row by position. */
  rowIndex?: number;
  /** Where the line starts, in canvas coordinates. */
  at: Point;
};

export type PointingNote = {
  text: string;
  x: number;
  y: number;
  /** Where the leader that offered the note started. */
  from?: Point;
  /** The drawn line the note carries on from. */
  onStroke?: number;
  /** Called out from a ring: the ring says what, not the line. */
  ringStroke?: number;
};

function inside(p: Point, b: Box): boolean {
  return p.x >= b.x && p.x <= b.x + b.width && p.y >= b.y && p.y <= b.y + b.height;
}

/** The ends a note's line could be pointing from, the far end first. */
function candidates(note: PointingNote, strokes: Point[][]): Point[] {
  if (note.ringStroke !== undefined) return [];
  const stroke = note.onStroke !== undefined ? strokes[note.onStroke] : undefined;
  if (stroke && stroke.length > 1) {
    const ends = [stroke[0]!, stroke[stroke.length - 1]!];
    const d = (p: Point) => Math.hypot(p.x - note.x, p.y - note.y);
    return ends.sort((a, b) => d(b) - d(a));
  }
  return note.from ? [note.from] : [];
}

/**
 * Where each written note's line starts, as a card and a row.
 *
 * The smallest card under the start wins, so a line from a table inside a
 * region names the table. A start outside every card points at nothing and
 * is left out: the ring or the sketch already says what that note is about.
 */
export function resolvePointers(
  notes: PointingNote[],
  strokes: Point[][],
  boxes: Box[],
  rowsOf: (nodeId: string) => RowBand[] | null,
): Pointer[] {
  const out: Pointer[] = [];
  for (const note of notes) {
    const text = note.text.trim();
    if (!text) continue;
    for (const at of candidates(note, strokes)) {
      const box = boxes
        .filter((b) => inside(at, b))
        .sort((a, b) => a.width * a.height - b.width * b.height)[0];
      if (!box) continue;
      const pointer: Pointer = { text, node: box.id, at };
      const rows = rowsOf(box.id);
      const index = rows ? rows.findIndex((r) => at.y >= r.top && at.y <= r.bottom) : -1;
      if (rows && index >= 0) {
        pointer.row = rows[index]!.key;
        pointer.rowIndex = index;
      }
      out.push(pointer);
      break;
    }
  }
  return out;
}

/** The pointers as a sentence, for a reader who only gets text. */
export function describePointers(pointers: Pointer[]): string {
  return pointers
    .map((p) => {
      const words = p.text.length > 48 ? `${p.text.slice(0, 47)}…` : p.text;
      return `"${words}" drawn from ${p.row !== undefined ? `row ${p.row} of ` : ""}${p.node}`;
    })
    .join("; ");
}
