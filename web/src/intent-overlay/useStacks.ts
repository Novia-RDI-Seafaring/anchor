import { describeCuts, resolveCuts } from "./cuts";
import {
  blobAround,
  insidePolygon,
  type Point
} from "./lasso";
import { describePointers, resolvePointers } from "./pointers";
import { describeSketch, resolveSketch } from "./sketch";
import { describeStrikes, resolveStrikes } from "./strikes";
import { type Queued, type Stack } from "./markupStore";
import { BLOB_PAD_PX } from "./constants";
import { noteRect, rectCorners } from "./geometry";
import type { MarkupModel } from "./types";

export function useStacks(context: Pick<MarkupModel, "markupStore" | "settledNotes" | "boxes" | "rowsOf" | "edgesOf" | "getViewport" | "surfaceRef" | "setViewport" | "setCurrent" | "setMarquee" | "sending" | "onFiled" | "ids" | "host">) {
  const { markupStore, settledNotes, boxes, rowsOf, edgesOf, getViewport, surfaceRef, setViewport, setCurrent, setMarquee, sending, onFiled, ids, host } = context;
  /** The live remark as it would be queued, without queueing it. */
  const snapshot = (text: string, id = `q${Date.now()}`): Queued => {
    // The notes are taken as they stand on screen -- called out beside a
    // card, with the leader that reaches them -- since after queueing
    // nothing recomputes either, and the words used to jump to where they
    // were first offered and lose their line.
    const drawn = markupStore.getState().marks;
    const written = settledNotes.filter((n) => n.text.trim());
    const sketch = resolveSketch(
      drawn.map((m) => m.points),
      written,
      boxes,
    );
    const cuts = resolveCuts(drawn.map((m) => m.points), boxes, rowsOf);
    const strikes = resolveStrikes(drawn.map((m) => m.points), edgesOf());
    return { id, text, ids, sketch, cuts, strikes, marks: drawn, notes: written };
  };

  /** Where a set-aside remark's ground lies, in canvas coordinates. */
  const blobOf = (st: Pick<Stack, "marks" | "notes" | "ids">): Point[] | null => {
    const corners: Point[] = [
      ...st.marks.flatMap((m) => m.points),
      ...st.notes.filter((n) => n.inStroke === undefined).flatMap((n) => rectCorners(noteRect(n))),
      ...boxes.filter((b) => st.ids.includes(b.id)).flatMap(rectCorners),
    ];
    if (corners.length < 3) return null;
    const shape = blobAround(corners, BLOB_PAD_PX / Math.max(0.2, getViewport().zoom));
    return shape.length >= 3 ? shape : null;
  };

  /** The set-aside remark whose ground is under a canvas point, if any. */
  const shelfAt = (at: Point): string | null => {
    const hit = markupStore.getState().shelf.find((st) => {
      const b = blobOf(st);
      return b ? insidePolygon(at, b) : false;
    });
    return hit?.id ?? null;
  };

  /** Bring a remark's ground into view when it is off the screen. */
  const reveal = (st: Pick<Stack, "marks" | "notes" | "ids">) => {
    const b = blobOf(st);
    const el = surfaceRef.current;
    if (!b || !el) return;
    const vp = getViewport();
    const xs = b.map((pt) => pt.x * vp.zoom + vp.x);
    const ys = b.map((pt) => pt.y * vp.zoom + vp.y);
    const r = el.getBoundingClientRect();
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    if (x0 >= 0 && y0 >= 0 && x1 <= r.width && y1 <= r.height) return;
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    setViewport({ zoom: vp.zoom, x: vp.x + r.width / 2 - cx, y: vp.y + r.height / 2 - cy }, { duration: 300 });
  };

  const liveSnapshot = () => snapshot(markupStore.getState().notes.map((note) => note.text.trim()).filter(Boolean).join("\n\n"));

  const newStack = () => {
    const state = markupStore.getState();
    if (state.marks.length === 0 && !state.notes.some((note) => note.text.trim())) return;
    markupStore.getState().newStack(liveSnapshot());
    setCurrent(null);
    setMarquee(null);
  };

  const switchTo = (id: string) => {
    if (!markupStore.getState().shelf.some((stack) => stack.id === id)) return;
    markupStore.getState().switchStack(id, liveSnapshot());
    setCurrent(null);
    setMarquee(null);
  };

  /**
     * The remark goes to the agent as it stands, and its ink fades to a
     * ghost that stays until the intent is resolved.
     *
     * There used to be a queue between drawing and sending, so that sending
     * each thought would not wake the agent once per thought. The agent
     * listens now, and a remark is the unit of work: one remark can hold as
     * many rings, lines and words as the reader likes before they press send,
     * so batching happens on the board, not in a list. The next stroke after
     * sending is the next remark.
     */
  const sendRemark = async () => {
    if (sending) return;
    const q = snapshot(markupStore.getState().notes.map((n) => n.text.trim()).filter(Boolean).join("\n\n"));
    try {
      // The words, then the shape of the drawing under them. Both, because
      // not every reader will parse a structure and the two must never
      // disagree about what was drawn.
      const pointers = resolvePointers(q.notes, q.marks.map((m) => m.points), boxes, rowsOf);
      const drawn = [describeSketch(q.sketch), describeCuts(q.cuts), describeStrikes(q.strikes), describePointers(pointers)]
        .filter(Boolean)
        .join("\n");
      // A struck edge's two ends are what the ask is about, so they are
      // targets too: the cross itself caught no card.
      const ends = q.strikes.flatMap((k) => [k.source, k.target]);
      const sent = await markupStore.getState().send(q, () => host.thread.submit({
        text: !drawn ? q.text : q.text ? `${q.text}\n\n--- drawn ---\n${drawn}` : drawn,
        targetIds: Array.from(new Set([...q.ids, ...ends, ...pointers.map((pt) => pt.node)])),
        ...(q.sketch.nodes.length > 0 ? { sketch: q.sketch } : {}),
        ...(q.cuts.length > 0 ? { cuts: q.cuts } : {}),
        ...(q.strikes.length > 0 ? { strikes: q.strikes } : {}),
        ...(pointers.length > 0 ? { pointers } : {}),
      }));
      // Sent, not gone: the remark stays on the board as the place its own
      // outcome will appear.
      if (sent) {
        setCurrent(null);
        setMarquee(null);
        onFiled?.();
      }
    } catch (err) {
      // The remark is still on the board, untouched, so nothing is lost.
      window.alert(`Not sent: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return { blobOf, shelfAt, reveal, newStack, switchTo, sendRemark };
}
