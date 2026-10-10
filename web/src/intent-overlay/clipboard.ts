import { markHits, type Box, type Point } from "./lasso";
import type { Mark, MarkupState, Note, Selection } from "./markupStore";

export type MarkupFragment = { marks: Mark[]; notes: Note[] };

/** Copy the whole drawn gesture, including its hosted words and leaders. */
export function markupSelection(state: Pick<MarkupState, "marks" | "notes">, selection: Selection): Selection {
  const strokes = new Set(selection.strokes.filter((i) => state.marks[i]));
  const notes = new Set(selection.notes);
  let grew = true;
  while (grew) {
    grew = false;
    for (const note of state.notes) {
      const linked = [note.inStroke, note.onStroke, note.ringStroke].filter((i): i is number => i !== undefined && !!state.marks[i]);
      if (!notes.has(note.id) && !linked.some((i) => strokes.has(i))) continue;
      if (!notes.has(note.id)) { notes.add(note.id); grew = true; }
      for (const i of linked) if (!strokes.has(i)) { strokes.add(i); grew = true; }
    }
  }
  return { strokes: [...strokes].sort((a, b) => a - b), notes: [...notes] };
}

export function captureMarkup(state: Pick<MarkupState, "marks" | "notes">, selection: Selection): MarkupFragment {
  const closed = markupSelection(state, selection);
  const indices = closed.strokes;
  const reindex = (i: number | undefined) => i === undefined ? undefined : indices.indexOf(i);
  return structuredClone({ marks: indices.map((i) => state.marks[i]!),
    notes: state.notes.filter((n) => closed.notes.includes(n.id)).map((n) => ({ ...n,
      inStroke: reindex(n.inStroke), onStroke: reindex(n.onStroke), ringStroke: reindex(n.ringStroke) })) });
}

/** Geometry is copied, but targets are determined again at the new location. */
export function appendMarkup(state: Pick<MarkupState, "marks" | "notes">, fragment: MarkupFragment, offset: Point, boxes: Box[], freshId: () => string = () => crypto.randomUUID()) {
  const shift = (p: Point): Point => ({ x: p.x + offset.x, y: p.y + offset.y });
  const reindex = (i: number | undefined) => i === undefined ? undefined : state.marks.length + i;
  const copiedMarks = fragment.marks.map((mark) => ({ color: mark.color, points: mark.points.map(shift) }));
  const copiedNotes = fragment.notes.map((note) => ({ ...structuredClone(note), ...shift(note), id: freshId(),
    from: note.from ? shift(note.from) : undefined, offered: false, pinned: true,
    inStroke: reindex(note.inStroke), onStroke: reindex(note.onStroke), ringStroke: reindex(note.ringStroke) }));
  const marks = [...state.marks, ...copiedMarks];
  const selected = { strokes: copiedMarks.map((_, i) => state.marks.length + i), notes: copiedNotes.map((n) => n.id) };
  return { marks, notes: [...state.notes, ...copiedNotes], selected, manual: null,
    ids: markHits(marks.map((m) => m.points), boxes), editing: null, activeLabel: null };
}
