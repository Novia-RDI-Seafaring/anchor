import { resolveCuts } from "@/canvas/cuts";
import {
  blobAround,
  isLoop,
  type Point
} from "@/canvas/lasso";
import { previewOps, type Preview } from "@/canvas/preview";
import { resolveSketch } from "@/canvas/sketch";
import { resolveStrikes } from "@/canvas/strikes";
import { BLOB_PAD_PX, GHOST_H, GHOST_W } from "./constants";
import { noteRect, rectCorners } from "./geometry";
import type { MarkupModel } from "./types";

export function deriveMarkupRender(context: Pick<MarkupModel, "current" | "strokes" | "screen" | "filed" | "boxes" | "viewport" | "kept" | "storeNodes" | "storeEdges" | "notes" | "marks" | "rowsOf" | "edgesOf" | "notePos" | "ids" | "selectionRect" | "selected">) {
  const { current, strokes, screen, filed, boxes, viewport, kept, storeNodes, storeEdges, notes, marks, rowsOf, edgesOf, notePos, ids, selectionRect, selected } = context;
  const looping = current ? isLoop(current) : false;

  const all = current ? [...strokes, current] : strokes;

  const paths = all.map((st) => st.map(screen));

  /**
     * Each filed remark's ghost: ink, shape, and everything the thread has put
     * on the board -- placed messages as ghost nodes, questions, the pending
     * suggestion. Worked out per render so it follows the poll.
     */
  const ghosts = filed.map((f) => {
    const items = f.intent?.items ?? [];
    const corners: Point[] = [
      ...f.marks.flatMap((m) => m.points),
      // The cards the remark caught. Without them the shape shrank to the
      // stroke the moment it was sent, and the status line landed on the
      // table it was about instead of beneath the whole of it.
      ...boxes.filter((b) => f.ids.includes(b.id)).flatMap(rectCorners),
      ...f.notes.filter((n) => n.inStroke === undefined).flatMap((n) => rectCorners(noteRect(n))),
      ...items.flatMap((it) =>
        it.place && it.type === "message" && it.state !== "done"
          ? [
            { x: it.place.x, y: it.place.y },
            {
              x: it.place.x + (it.place.width ?? GHOST_W),
              y: it.place.y + (it.place.height ?? GHOST_H),
            },
          ]
          : [],
      ),
    ];
    const pad = BLOB_PAD_PX / Math.max(0.2, viewport.zoom);
    const blob = corners.length >= 3 ? blobAround(corners, pad) : null;
    const status = [...items]
      .reverse()
      .find((it) => it.type === "message" && !it.place && it.author.kind !== "human");
    const questions = items.filter((it) => it.type === "question" && it.state === "open");
    const suggestion = [...items].reverse().find(
      (it) => it.type === "suggestion" && it.state === "pending",
    );
    // Act, then ask: a change the agent applied itself, which the reader has
    // not yet kept or put back. The result is on the canvas; the question is
    // only whether it stays.
    const applied =
      f.intent?.status === "resolved"
        ? undefined
        : [...items].reverse().find(
          (it) =>
            it.type === "suggestion" &&
            it.state === "applied" &&
            it.author.kind !== "human" &&
            !kept.has(it.id),
        );
    // Once there is a proposal, the plan has become the result: the agent's
    // ghost boxes stand down and the ops are drawn where they will land.
    const preview: Preview | null = suggestion?.ops
      ? previewOps(suggestion.ops, storeNodes, Object.values(storeEdges))
      : null;
    const placed = preview
      ? []
      : items.filter((it) => it.place && it.type === "message" && it.state !== "done");
    return { f, blob, status, questions, suggestion, applied, placed, items, preview };
  });

  // A mark with no words points at something without saying what about it.
  const written = notes.map((n) => n.text.trim()).filter(Boolean).join("\n\n");

  const cutsReading = resolveCuts(marks.map((m) => m.points), boxes, rowsOf);

  const strikesReading = resolveStrikes(marks.map((m) => m.points), edgesOf());

  // Some marks say it all by themselves. A cross over an edge or a line
  // through a table is the whole ask; demanding words as well made the
  // clearest gesture on the board the one that could not be sent.
  const sayable = Boolean(written) || cutsReading.length > 0 || strikesReading.length > 0;

  // Which shapes offer handles: the one under the pointer, and any that is
  // holding words. Closed shapes only -- a line has no box to pull on.
  // Strokes that belong to a label. They are not marks in their own right:
  // the label owns them, carries them when it moves and takes them when it is
  // deleted. Offering them their own cross put two of them on one gesture,
  // one at the end of the line and one on the words.
  /**
   * Words for highlights on a card, called out down its sides.
   *
   * Worked out on every render rather than stored, so they re-flow when one
   * is added or removed: the remaining remarks spread back out over the card
   * instead of leaving a gap where a deleted one used to be.
   */

  /**
   * Everything this remark covers: the ink, the words, and the cards caught.
   *
   * Drawn as one quiet shape behind the lot, so the marks read as one remark
   * and the button that files them has something to belong to.
   */
  const remarkBlob = (() => {
    if (!sayable) return null;
    const corners: Point[] = [
      ...strokes.flat(),
      ...notes
        .filter((n) => n.inStroke === undefined)
        .flatMap((n) => rectCorners(noteRect({ ...n, ...notePos(n) }))),
      ...boxes.filter((b) => ids.includes(b.id)).flatMap(rectCorners),
    ];
    if (corners.length < 3) return null;
    const pad = BLOB_PAD_PX / Math.max(0.2, viewport.zoom);
    const shape = blobAround(corners, pad);
    return shape.length >= 3 ? shape : null;
  })();

  /**
     * The drawing as it currently reads, shown before it is filed.
     *
     * The reader is standing right here: if the shape of what they drew has
     * come out wrong, one line of readback lets them fix it in the second
     * before they send, which is worth more than any amount of interpretation
     * at the other end. It also makes "the structure was lost" and "the
     * structure was never read" tell each other apart, which from the filed
     * intent alone they do not.
     */
  const reading = resolveSketch(
    marks.map((m) => m.points),
    notes.filter((n) => n.text.trim()),
    boxes,
  );

  const picked = selectionRect();

  // Exactly one stroke and nothing else: it wears its controls on its own ink
  // rather than inside a box drawn round it.
  const lone =
    selected.strokes.length === 1 && selected.notes.length === 0
      ? selected.strokes[0]!
      : null;

  return { looping, all, paths, ghosts, written, cutsReading, strikesReading, sayable, remarkBlob, reading, picked, lone };
}
