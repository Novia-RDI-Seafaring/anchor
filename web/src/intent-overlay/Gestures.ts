import {
  fitStroke,
  markHits,
  MIN_BOX_PX,
  remapPoint,
  remapStroke,
  strokeBounds,
  translateStroke,
  unionRect,
  type Point,
  type Rect
} from "./lasso";
import { type Note, type Selection } from "./markupStore";
import { noteRect } from "./geometry";
import type { MarkupModel } from "./types";
import { appendMarkup, captureMarkup } from "./clipboard";

export function useSelectionGestures(context: Pick<MarkupModel, "markupStore" | "applyMarks" | "setIds" | "manual" | "boxes" | "selected" | "groupDrag" | "toFlow" | "setNotes" | "getViewport" | "drewJustNow" | "settledNotes">) {
  const { markupStore, applyMarks, setIds, manual, boxes, selected, groupDrag, toFlow, setNotes, getViewport, drewJustNow } = context;
  /** Put a stroke back with new geometry, leaving everything else alone. */
  const replaceStroke = (index: number, points: Point[]) => {
    if (!markupStore.getState().marks[index]) return;
    applyMarks(
      markupStore.getState().marks.map((m, i) => (i === index ? { ...m, points } : m)),
    );
    setIds(manual ?? markHits(markupStore.getState().marks.map((mark) => mark.points), boxes));
  };

  /**
     * Make a drawn shape tall enough for what has been written in it.
     *
     * It grows downward, keeping the top edge where the reader put it, because
     * the words start at the top and growth should push the bottom away rather
     * than move the whole shape out from under the cursor.
     */
  const growHost = (index: number, neededHeight: number) => {
    const stroke = markupStore.getState().marks.map((mark) => mark.points)[index];
    if (!stroke) return;
    const b = strokeBounds(stroke);
    if (b.height >= neededHeight - 0.5) return;
    replaceStroke(index, fitStroke(stroke, { ...b, height: neededHeight }));
  };

  /**
     * What the selection covers: every mark in it, as one box.
     *
     * Handles hang off this rather than off each mark, so a group scales by one
     * transform and a stroke in the corner of the selection stays in the corner
     * instead of being stretched to fill the whole box on its own.
     */
  const rectOf = (sel: Selection): Rect | null =>
    unionRect([
      ...sel.strokes
        .map((i) => markupStore.getState().marks.map((mark) => mark.points)[i])
        .filter((st): st is Point[] => st !== undefined)
        .map(strokeBounds),
      ...sel.notes
        .map((id) => markupStore.getState().notes.find((n) => n.id === id))
        .filter((n): n is Note => n !== undefined)
        .map(noteRect),
    ]);

  const selectionRect = (): Rect | null => rectOf(selected);

  /**
     * Start dragging the selection, to move it or to resize it.
     *
     * The marks are captured as they were when the drag began and the transform
     * is applied to THOSE each time, rather than to the result of the last move.
     * Compounding the transform instead would let rounding accumulate, and a
     * shape dragged back and forth would slowly wander and distort.
     *
     * The pointer is captured on the handle: without it, the first move outside
     * the little square lands on the drawing surface and starts a new stroke
     * across the very thing being dragged.
     */
  const startGroupDrag =
    (mode: "move" | "resize", corner?: { x: 0 | 1; y: 0 | 1 }, over?: Selection) =>
      (e: React.PointerEvent) => {
        e.preventDefault();
        e.stopPropagation();
        // A tab on one stroke drags that stroke. The handles on the selection
        // drag the selection. Same machinery, different set of marks.
        let sel = over ?? selected;
        if (mode === "move" && e.altKey) {
          const state = markupStore.getState();
          const copy = appendMarkup(state, captureMarkup({ ...state, notes: context.settledNotes }, sel), { x: 0, y: 0 }, boxes);
          markupStore.setState(copy);
          sel = copy.selected;
        }
        const from = rectOf(sel);
        if (!from) return;
        groupDrag.current = {
          mode,
          from,
          start: toFlow(e),
          anchor: corner
            ? {
              x: corner.x === 0 ? from.x + from.width : from.x,
              y: corner.y === 0 ? from.y + from.height : from.y,
            }
            : { x: from.x, y: from.y },
          strokes: sel.strokes
            .map((i) => [i, markupStore.getState().marks.map((mark) => mark.points)[i]] as const)
            .filter((pair): pair is readonly [number, Point[]] => pair[1] !== undefined),
          notes: sel.notes
            .map((id) => markupStore.getState().notes.find((n) => n.id === id))
            .filter((n): n is Note => n !== undefined)
            .map((n) => [n.id, { x: n.x, y: n.y }] as const),
        };
        e.currentTarget.setPointerCapture(e.pointerId);
      };

  const onGroupDragMove = (e: React.PointerEvent) => {
    const g = groupDrag.current;
    if (!g) return;
    e.stopPropagation();
    const p = toFlow(e);
    const to: Rect =
      g.mode === "move"
        ? { ...g.from, x: g.from.x + (p.x - g.start.x), y: g.from.y + (p.y - g.start.y) }
        : (() => {
          const width = Math.max(MIN_BOX_PX, Math.abs(p.x - g.anchor.x));
          const height = Math.max(MIN_BOX_PX, Math.abs(p.y - g.anchor.y));
          return {
            x: p.x < g.anchor.x ? g.anchor.x - width : g.anchor.x,
            y: p.y < g.anchor.y ? g.anchor.y - height : g.anchor.y,
            width,
            height,
          };
        })();

    const nextStrokes = [...markupStore.getState().marks.map((mark) => mark.points)];
    for (const [index, points] of g.strokes) {
      nextStrokes[index] =
        g.mode === "move"
          ? translateStroke(points, to.x - g.from.x, to.y - g.from.y)
          : remapStroke(points, g.from, to);
    }
    applyMarks(markupStore.getState().marks.map((m, i) => ({ ...m, points: nextStrokes[i]! })));
    setIds(manual ?? markHits(nextStrokes, boxes));
    if (g.notes.length > 0) {
      setNotes((prev) =>
        prev.map((n) => {
          const orig = g.notes.find(([id]) => id === n.id)?.[1];
          if (!orig) return n;
          const at = remapPoint(orig, g.from, to);
          return { ...n, x: at.x, y: at.y };
        }),
      );
    }
  };

  const endGroupDrag = (e: React.PointerEvent) => {
    const g = groupDrag.current;
    if (!g) return;
    groupDrag.current = null;
    e.stopPropagation();
    // Let go where it was pressed: a click, and the click that follows picks
    // the mark out. Let go somewhere else: a move, and the click that
    // follows is not a click.
    const p = toFlow(e);
    if (Math.hypot(p.x - g.start.x, p.y - g.start.y) * getViewport().zoom > 3) {
      drewJustNow.current = true;
    }
  };

  /**
     * Give everything picked out a new pen.
     *
     * Nothing picked out means nothing to recolour -- the key has already set
     * the pen in hand, which is what it does the rest of the time.
     */


  /**
   * Carry a label somewhere else, and let its leader follow.
   *
   * Only the far end moves. The line keeps the end it started from, so it
   * pivots and stretches about that point, and the words re-lean to carry on
   * the new angle -- which is what a leader is for. Dragging a label that was
   * simply sitting at the end of a drawn line pulls it off that end, so the
   * connector appears: the reader has separated the two, and a line is what
   * says they still belong together.
   */
  const moveLabel = (id: string, to: Point) => markupStore.getState().moveLabel(id, to, boxes);

  /**
     * Take a label and the line it belongs to.
     *
     * The line was drawn to reach the words; without them it is a stroke
     * pointing at nothing, left behind to be tidied up by hand. A label at the
     * end of an offered leader needs no such care -- that leader is drawn from
     * the note itself, so it goes when the note does.
     */
  /**
   * Take strokes off the board, and everything hanging off them.
   *
   * A highlight is one gesture drawn as three marks: the ring, the line
   * out of it, and the words at the end. Deleting any one of them deletes
   * the gesture; leaving a ring with no words is a circle round something
   * for no stated reason, and leaving words with no ring is a remark about
   * nothing. So the set to remove is closed over those links first. Notes
   * point at strokes by index, and dropping some shifts the rest, which
   * every path here used to get subtly wrong for one of the three kinds.
   */
  const dropMarks = (strokes: Iterable<number>, noteIds: Iterable<string> = []) => markupStore.getState().dropMarks(strokes, noteIds, boxes);

  const removeLabel = (id: string) => dropMarks([], [id]);

  /** Erase everything in the selection at once. */
  const removeSelected = () => dropMarks(selected.strokes, selected.notes);

  /** Remove one stroke, and the gesture it was part of. */
  const removeStroke = (index: number) => dropMarks([index]);

  return { growHost, selectionRect, startGroupDrag, onGroupDragMove, endGroupDrag, moveLabel, removeLabel, removeSelected, removeStroke };
}
