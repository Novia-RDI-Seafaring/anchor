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
import { ghostOutlineKind, type PaintRect } from "./paintGeometry";

/**
 * Compute the normalised rect (top-left + size) from a pointer-down and a
 * pointer-current position. Pure; shared by ghost rendering AND the actual
 * drop math so the WYSIWYG contract holds — if the ghost shows `{left:200,
 * top:300, width:200, height:200}`, the dropped node lands at the matching
 * flow-space rect (per `paintFlowRect`).
 */
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
