import { useEffect, useRef } from "react";
import type { Box, Point } from "./lasso";
import type { Filed } from "./markupStore";
import type { OverlayHost, ThreadItem, Viewport } from "./ports";
import { noteRect } from "./geometry";
import { awaitingVerdict } from "./verdict";

type Rect = { x: number; y: number; width: number; height: number };

/** What a remark holds for the reader right now; null when nothing. */
export function waitingFor(remark: Filed, kept: ReadonlySet<string>): ThreadItem | null {
  const items = remark.intent?.items ?? [];
  const question = [...items].reverse().find((it) => it.type === "question" && it.state === "open");
  const pending = [...items].reverse().find((it) => it.type === "suggestion" && it.state === "pending");
  return question ?? pending ?? awaitingVerdict(remark.intent, kept).at(-1) ?? null;
}

/** Everything a remark covers on the board: its ink, its words, its cards, what changed. */
export function boundsOf(remark: Filed, boxes: Box[], host: OverlayHost, kept: ReadonlySet<string>): Rect | null {
  const applied = awaitingVerdict(remark.intent, kept).at(-1);
  const changes = applied ? host.display.changes?.(applied) ?? null : null;
  const touched = new Set([...remark.ids, ...(changes?.marks ?? []).map((m) => m.id)]);
  const rects: Rect[] = [
    ...boxes.filter((b) => touched.has(b.id)),
    ...(changes?.removed.nodes ?? []),
    ...remark.notes.filter((n) => n.inStroke === undefined).map(noteRect),
  ];
  const points: Point[] = [
    ...remark.marks.flatMap((m) => m.points),
    ...rects.flatMap((r) => [{ x: r.x, y: r.y }, { x: r.x + r.width, y: r.y + r.height }]),
  ];
  if (points.length === 0) return null;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y };
}

function contains(outer: Rect, inner: Rect): boolean {
  return inner.x >= outer.x && inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width && inner.y + inner.height <= outer.y + outer.height;
}

/**
 * Back to where the reader asked from.
 *
 * The view they had when they sent the remark is the view they framed the
 * ask in, so that is where the answer is shown. Only when the change reaches
 * outside it does the view widen, just enough to take the change in too.
 */
export function returnTo(remark: Filed, boxes: Box[], host: OverlayHost, kept: ReadonlySet<string>) {
  const { geometry } = host;
  const saved = remark.intent?.payload?.viewport as Viewport | undefined;
  const bounds = boundsOf(remark, boxes, host, kept);
  const pane = geometry.paneSize?.() ?? null;
  const duration = 450;
  if (!saved || typeof saved.zoom !== "number") {
    if (bounds) void geometry.fitBounds?.(bounds, { padding: 0.2, duration });
    return;
  }
  if (bounds && pane) {
    const seen = { x: -saved.x / saved.zoom, y: -saved.y / saved.zoom,
      width: pane.width / saved.zoom, height: pane.height / saved.zoom };
    if (!contains(seen, bounds)) {
      const x = Math.min(seen.x, bounds.x);
      const y = Math.min(seen.y, bounds.y);
      const width = Math.max(seen.x + seen.width, bounds.x + bounds.width) - x;
      const height = Math.max(seen.y + seen.height, bounds.y + bounds.height) - y;
      void geometry.fitBounds?.({ x, y, width, height }, { padding: 0.05, duration });
      return;
    }
  }
  void geometry.setViewport(saved, { duration });
}

/**
 * A reply that arrives while the pen is down picks it back up.
 *
 * The reader left intent mode to wait. When the agent answers, the board
 * goes straight back to the remark, with the change on the canvas and keep
 * beside it, rather than putting a notice in between.
 *
 * Only answers that arrive while the page is open: what was already
 * waiting when a remark was first seen does not pull the reader away.
 */
export function useReplyReturn({ active, filed, kept, boxes, host, onEnter }: {
  active: boolean;
  filed: Filed[];
  kept: ReadonlySet<string>;
  boxes: Box[];
  host: OverlayHost;
  onEnter?: () => void;
}) {
  const last = useRef(new Map<string, string | null>());
  const pending = useRef<Filed | null>(null);
  useEffect(() => {
    let arrived: Filed | null = null;
    for (const remark of filed) {
      const now = waitingFor(remark, kept)?.id ?? null;
      const known = last.current.has(remark.intentId);
      const before = last.current.get(remark.intentId) ?? null;
      last.current.set(remark.intentId, now);
      if (known && now && now !== before) arrived = remark;
    }
    if (arrived && !active && onEnter) {
      pending.current = arrived;
      onEnter();
    }
  }, [filed, kept, active, onEnter]);

  // Moved once the mode is on, so the change and its keep are drawn as the
  // view arrives.
  useEffect(() => {
    if (!active || !pending.current) return;
    const remark = pending.current;
    pending.current = null;
    returnTo(remark, boxes, host, kept);
  }, [active, boxes, host, kept]);
}
