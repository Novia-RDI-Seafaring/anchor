export type PaintRect = {
  /** Screen-space top-left (CSS pixels, fixed positioning origin). */
  left: number;
  top: number;
  width: number;
  height: number;
};

/** Normalize a pointer drag into a top-left plus size rectangle. */
export function paintRectFrom(
  down: { x: number; y: number },
  current: { x: number; y: number },
): PaintRect {
  const left = Math.min(down.x, current.x);
  const top = Math.min(down.y, current.y);
  const width = Math.abs(current.x - down.x);
  const height = Math.abs(current.y - down.y);
  return { left, top, width, height };
}

/** Maximum pointer movement that still counts as click-to-place. */
export const PAINT_DRAG_THRESHOLD_PX = 4;

export function ghostIsSquare(nodeType: string | null): boolean {
  return nodeType === "entity";
}

/** Constrain a drag rectangle to a square anchored at pointer-down. */
export function maybeSquareRect(
  rect: PaintRect,
  down: { x: number; y: number },
  square: boolean,
): PaintRect {
  if (!square) return rect;
  const side = Math.max(rect.width, rect.height);
  const left = rect.left === down.x ? down.x : down.x - side;
  const top = rect.top === down.y ? down.y : down.y - side;
  return { left, top, width: side, height: side };
}

export function ghostOutlineKind(
  nodeType: string | null,
): "rect" | "circle" | "diamond" | "dashed" {
  switch (nodeType) {
    case "concept":
    case "spec":
    case "note":
    case "fact":
      return "rect";
    case "entity":
      return "circle";
    case "funnel":
      return "diamond";
    case "area":
      return "dashed";
    default:
      return "dashed";
  }
}
