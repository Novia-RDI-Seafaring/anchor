/**
 * The cards an answer put on the board, kept clear of the remark's ink.
 *
 * A remark's ink sits above the canvas, so the cards the agent places inside
 * the remark arrived under its tint, its strokes and its words, and read as
 * if half transparent. The answer is what the reader came to read: the
 * remark's ink stays everywhere else and leaves those cards alone.
 */
import type { Changes } from "./ports";
import type { Box, Point } from "./strokeGeometry";

type Rect = { x: number; y: number; w: number; h: number };

/** Room around a card, so its outline and badge stay clear too. */
const PAD = 6;

/** The answered cards, in screen space. */
export function answeredCards(
  ghosts: { changes?: Changes | null }[],
  boxes: Box[],
  screen: (p: Point) => Point,
  zoom: number,
): Rect[] {
  const ids = new Set(ghosts.flatMap((g) => (g.changes?.marks ?? [])
    .filter((m) => m.element === "node")
    .map((m) => m.id)));
  return boxes.filter((b) => ids.has(b.id)).map((b) => {
    const at = screen({ x: b.x, y: b.y });
    return { x: at.x - PAD, y: at.y - PAD, w: b.width * zoom + PAD * 2, h: b.height * zoom + PAD * 2 };
  });
}

/** A clip path that keeps everything but the given cards. */
export function outsideCards(cards: Rect[]): string | undefined {
  if (!cards.length) return undefined;
  const far = 1e6;
  const holes = cards.map((c) => `M${c.x} ${c.y}h${c.w}v${c.h}h${-c.w}Z`).join("");
  return `path(evenodd, "M${-far} ${-far}H${far}V${far}H${-far}Z${holes}")`;
}
