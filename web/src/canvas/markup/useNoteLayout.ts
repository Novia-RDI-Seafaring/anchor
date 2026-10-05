import {
  calloutPlaces,
  exitLoop,
  lassoHits,
  loopCentre,
  ringOutline,
  type CalloutPlace,
  type Point,
  type Rect
} from "@/canvas/lasso";
import { type Note } from "@/stores/markupStore";
import { CALLOUT_GAP_PX } from "./constants";
import type { MarkupModel } from "./types";

export function useNoteLayout(context: Pick<MarkupModel, "notes" | "strokes" | "boxes" | "viewport" | "surfaceRef" | "toFlow">) {
  const { notes, strokes, boxes, viewport, surfaceRef, toFlow } = context;
  const calledOut = (() => {
    const byNode = new Map<string, { id: string; centre: Point }[]>();
    for (const n of notes) {
      if (n.pinned || n.ringStroke === undefined) continue;
      const ring = strokes[n.ringStroke];
      if (!ring) continue;
      // Called out only when the ring is about ONE card. A ring round two
      // put its words "beside the first card" -- which was the gap between
      // them, inside the ring, looking for all the world like a text box.
      // Several cards keep the clear-space placement outside the ring.
      const hits = lassoHits(ring, boxes);
      if (hits.length !== 1) continue;
      const on = hits[0]!;
      const list = byNode.get(on) ?? [];
      list.push({ id: n.id, centre: loopCentre(ringOutline(ring)) });
      byNode.set(on, list);
    }
    const out = new Map<string, CalloutPlace>();
    const gap = CALLOUT_GAP_PX / Math.max(0.2, viewport.zoom);
    for (const [nodeId, items] of byNode) {
      const node = boxes.find((b) => b.id === nodeId);
      if (!node) continue;
      for (const [id, place] of calloutPlaces(items, node, gap)) out.set(id, place);
    }
    return out;
  })();

  /** Where a note actually sits: called out by rule, or where it was carried. */
  const notePos = (n: Note): Point => {
    const place = calledOut.get(n.id);
    return place ? { x: place.x, y: place.y } : { x: n.x, y: n.y };
  };

  /**
     * Where a note's line begins.
     *
     * For a note that belongs to a ring this is recomputed rather than stored:
     * from the ring's centre, out through wherever the words are now, cut at
     * the outline. Storing the edge point would fix the line to one spot on the
     * rim, and carrying the words round to the far side would leave it hooking
     * back on itself.
     */
  const lineFrom = (n: Note): Point | undefined => {
    if (n.ringStroke === undefined) return n.from;
    const ring = strokes[n.ringStroke];
    if (!ring) return n.from;
    const outline = ringOutline(ring);
    if (outline.length < 3) return n.from;
    return exitLoop(outline, loopCentre(outline), notePos(n));
  };

  const settledNotes = notes.map((note) => ({
    ...note, ...notePos(note), from: lineFrom(note) ?? note.from,
  }));

  /**
     * Everything outside the visible canvas, as four occupied bands.
     *
     * An offer that lands off screen is an offer nobody sees: the ring's left
     * side was clear in canvas terms and under the tool rail in real ones. The
     * inset keeps the words off the rails and panels that sit over the edges.
     */
  const offScreen = (): Rect[] => {
    const el = surfaceRef.current;
    if (!el) return [];
    const r = el.getBoundingClientRect();
    const inset = 64;
    const tl = toFlow({ clientX: r.left + inset, clientY: r.top + inset });
    const br = toFlow({ clientX: r.right - inset, clientY: r.bottom - inset });
    const big = 1e6;
    return [
      { x: tl.x - big, y: tl.y - big, width: big, height: big * 2 },
      { x: br.x, y: tl.y - big, width: big, height: big * 2 },
      { x: tl.x - big, y: tl.y - big, width: big * 2, height: big },
      { x: tl.x - big, y: br.y, width: big * 2, height: big },
    ];
  };

  // Flow coordinates to this overlay's own pixels. The overlay and the canvas
  // fill the same box, so the transform maps straight across.
  const screen = (p: Point) => ({
    x: p.x * viewport.zoom + viewport.x,
    y: p.y * viewport.zoom + viewport.y,
  });

  return { calledOut, notePos, lineFrom, settledNotes, offScreen, screen };
}
