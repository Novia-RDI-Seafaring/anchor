/**
 * PaintGhost — WYSIWYG preview for the "armed-tool" placement gesture.
 *
 * While the user holds the pointer down on the canvas with a shape tool
 * armed, CanvasGraph renders this overlay at the in-flight rect so the
 * drop is no longer a "guess where it'll land" exercise. The outline
 * mirrors the shape's actual silhouette — rounded-rect for concept / area
 * / spec / note / fact, circle for entity, polygon-clipped rhombus for
 * funnel (diamond) — using the same CSS the real renderer uses. Anything
 * the registry doesn't know about renders as a generic dashed rectangle.
 *
 * Positioning: pixel coordinates in the viewport (CSS `fixed`). CanvasGraph
 * passes the raw `clientX/clientY` deltas straight through; we don't need
 * the flow → screen conversion because the ghost only exists during the
 * drag, and the cursor IS at `clientX/clientY` by definition. Using fixed
 * positioning sidesteps the canvas wrapper offsets (header, toolbar) and
 * the ReactFlow viewport's CSS transform.
 *
 * `pointer-events-none` so the ghost never swallows the pointer-up event;
 * the gesture lives on CanvasGraph's wrapper.
 */
export type PaintRect = {
  /** Screen-space top-left (CSS pixels, fixed positioning origin). */
  left: number;
  top: number;
  width: number;
  height: number;
};

/**
 * Compute the normalised rect (top-left + size) from a pointer-down and a
 * pointer-current position. Pure; shared by ghost rendering AND the actual
 * drop math so the WYSIWYG contract holds — if the ghost shows `{left:200,
 * top:300, width:200, height:200}`, the dropped node lands at the matching
 * flow-space rect (per `paintFlowRect`).
 */
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

/**
 * Pixel threshold below which a pointer-down/up pair is treated as a
 * single-click placement (no drag-to-size). Mirrors the constant in
 * CanvasGraph so the two stay in lock-step.
 */
export const PAINT_DRAG_THRESHOLD_PX = 4;

/**
 * Should the armed tool render the ghost as a square (1:1) regardless of
 * cursor position? Entity (circle) does — its renderer collapses to a
 * single dimension and `NodeResizer` is locked to `keepAspectRatio`. Other
 * shapes accept any aspect.
 */
export function ghostIsSquare(nodeType: string | null): boolean {
  return nodeType === "entity";
}

/**
 * Constrain a free-aspect rect to a square anchored at the pointer-down
 * corner. Side length = max(width, height) — feels natural when the user
 * drags out into either quadrant. Returns the same rect when not square.
 */
export function maybeSquareRect(
  rect: PaintRect,
  down: { x: number; y: number },
  square: boolean,
): PaintRect {
  if (!square) return rect;
  const side = Math.max(rect.width, rect.height);
  // Anchor the square at the down corner: if the cursor went right/down,
  // the rect's left/top equal `down`; if left/up, they sit at `down - side`.
  const left = rect.left === down.x ? down.x : down.x - side;
  const top = rect.top === down.y ? down.y : down.y - side;
  return { left, top, width: side, height: side };
}

/**
 * Visual outline class for the ghost. Pulled out so the same dispatch
 * runs in tests without mounting React.
 */
export function ghostOutlineKind(nodeType: string | null): "rect" | "circle" | "diamond" | "dashed" {
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

type Props = {
  /** Screen-space rect to outline; null hides the ghost. */
  rect: PaintRect | null;
  /** Armed tool name. Drives the outline silhouette. */
  nodeType: string | null;
};

export function PaintGhost({ rect, nodeType }: Props) {
  if (!rect || !nodeType) return null;
  // Below 2 px in either dimension the outline reads as noise — hide it
  // (click-to-place uses the cursor itself as the affordance).
  if (rect.width < 2 && rect.height < 2) return null;
  const kind = ghostOutlineKind(nodeType);
  const style: React.CSSProperties = {
    position: "fixed",
    left: rect.left,
    top: rect.top,
    width: Math.max(rect.width, 1),
    height: Math.max(rect.height, 1),
    pointerEvents: "none",
    zIndex: 30,
  };
  if (kind === "diamond") {
    style.clipPath = "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)";
    style.background = "rgba(14, 165, 233, 0.08)";
    style.border = "2px solid #0ea5e9";
  } else if (kind === "circle") {
    style.borderRadius = "50%";
    style.background = "rgba(14, 165, 233, 0.08)";
    style.border = "2px dashed #0ea5e9";
  } else if (kind === "rect") {
    style.borderRadius = 8;
    style.background = "rgba(14, 165, 233, 0.08)";
    style.border = "2px dashed #0ea5e9";
  } else {
    // dashed/area/unknown
    style.borderRadius = 12;
    style.background = "rgba(14, 165, 233, 0.05)";
    style.border = "2px dashed #0ea5e9";
  }
  return <div aria-hidden style={style} data-testid="paint-ghost" />;
}
