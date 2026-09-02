/** Preview rendering for the directional quick-connect gesture. */

import { paletteEntries, type PaletteMeta } from "./registry";

export const DIRECTIONAL_PEER_GAP_PX = 80;

export type ConnectorDirection = "N" | "E" | "S" | "W";

/**
 * HoverPreview - faint silhouette of the would-be peer + connecting edge.
 *
 * Rendered in screen coordinates (the same space as `dragArrow`) so it
 * lines up with the dot it's anchored to without needing a ReactFlow
 * inner wrapper. The ghost mirrors `createPeer`'s offset math: same N/E/S/W
 * delta + `DIRECTIONAL_PEER_GAP_PX`, so the click handler lands the real node exactly
 * where the ghost sat (no perceptible jump on commit).
 *
 * Visual style: 30% opacity stroke, dashed outline, no fill - reads as
 * "preview" without competing with real nodes. The connector path uses
 * the same soft S-curve bezier math as `dragArrow` so the hover and drag
 * affordances feel like a single continuum.
 */
export function DirectionalConnectorPreview({
  direction,
  sourceType,
  srcW,
  srcH,
  srcFlowX,
  srcFlowY,
  dotScreen,
  flowToScreenPosition,
}: {
  direction: ConnectorDirection;
  sourceType: string;
  srcW: number;
  srcH: number;
  srcFlowX: number;
  srcFlowY: number;
  dotScreen: { x: number; y: number };
  flowToScreenPosition: (p: { x: number; y: number }) => { x: number; y: number };
}) {
  const offset = {
    N: { dx: 0, dy: -(srcH + DIRECTIONAL_PEER_GAP_PX) },
    E: { dx: srcW + DIRECTIONAL_PEER_GAP_PX, dy: 0 },
    S: { dx: 0, dy: srcH + DIRECTIONAL_PEER_GAP_PX },
    W: { dx: -(srcW + DIRECTIONAL_PEER_GAP_PX), dy: 0 },
  }[direction];

  // The ghost's flow-space top-left. Width/height mirror the source's so
  // the preview previews "another of these" - the obvious affordance for
  // a same-type clone.
  const ghostFlowX = srcFlowX + offset.dx;
  const ghostFlowY = srcFlowY + offset.dy;
  // Screen-space top-left + size. We snap the corners through
  // `flowToScreenPosition` rather than scaling locally so the ghost
  // tracks the viewport zoom for free.
  const tl = flowToScreenPosition({ x: ghostFlowX, y: ghostFlowY });
  const br = flowToScreenPosition({ x: ghostFlowX + srcW, y: ghostFlowY + srcH });
  const left = Math.min(tl.x, br.x);
  const top = Math.min(tl.y, br.y);
  const width = Math.abs(br.x - tl.x);
  const height = Math.abs(br.y - tl.y);
  const cx = left + width / 2;
  const cy = top + height / 2;

  // Bezier from the source dot to the ghost centre. Same maths as the
  // drag arrow - keeps the hover/drag visual language consistent.
  const a = dotScreen;
  const b = { x: cx, y: cy };
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const pull = Math.min(120, Math.hypot(dx, dy) * 0.4);
  // Pull the bezier control points along the dominant axis so vertical
  // (N/S) ghosts arc cleanly without sideways wobble.
  const horizontal = direction === "E" || direction === "W";
  const c1 = horizontal
    ? { x: a.x + Math.sign(dx) * pull, y: a.y }
    : { x: a.x, y: a.y + Math.sign(dy) * pull };
  const c2 = horizontal
    ? { x: b.x - Math.sign(dx) * pull, y: b.y }
    : { x: b.x, y: b.y - Math.sign(dy) * pull };

  return (
    <>
      <svg
        style={{
          position: "fixed",
          inset: 0,
          width: "100vw",
          height: "100vh",
          pointerEvents: "none",
          zIndex: 26,
        }}
        aria-hidden
        data-testid="directional-hover-edge"
      >
        <path
          d={`M ${a.x} ${a.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${b.x} ${b.y}`}
          stroke="#0ea5e9"
          strokeWidth={1.5}
          fill="none"
          opacity={0.3}
        />
      </svg>
      <div
        data-testid="directional-hover-ghost"
        style={{
          position: "fixed",
          left,
          top,
          width,
          height,
          pointerEvents: "none",
          opacity: 0.3,
          zIndex: 26,
        }}
        aria-hidden
      >
        <GhostGlyph sourceType={sourceType} />
      </div>
    </>
  );
}

/**
 * Outlined silhouette of the source's shape, scaled to fill the parent.
 *
 * Falls back to the QuickAddPopover's glyph vocabulary so the ghost reads
 * as "the same kind of thing as the source". For shapes whose silhouette
 * differs from a rectangle (circle, diamond, dashed container) we render
 * the actual SVG primitive scaled to the box - circles and diamonds will
 * look slightly squished on non-square nodes; a per-shape ghost renderer
 * (e.g. wrapping the real shape primitives in a "ghost" mode) is a
 * sensible follow-up if the squish becomes distracting.
 */
function GhostGlyph({ sourceType }: { sourceType: string }) {
  const all = [...paletteEntries("shapes"), ...paletteEntries("cards")];
  const meta: PaletteMeta | undefined = all.find((e) => e.name === sourceType)?.meta;
  const glyph = meta?.glyph;
  const common = {
    width: "100%",
    height: "100%",
    preserveAspectRatio: "none" as const,
  };
  const stroke = "#0ea5e9";
  const strokeWidth = 1.5;
  switch (glyph) {
    case "circle":
      return (
        <svg viewBox="0 0 100 100" {...common} fill="none">
          <ellipse cx="50" cy="50" rx="48" ry="48" stroke={stroke} strokeWidth={strokeWidth} />
        </svg>
      );
    case "diamond":
      return (
        <svg viewBox="0 0 100 100" {...common} fill="none">
          <polygon points="50,2 98,50 50,98 2,50" stroke={stroke} strokeWidth={strokeWidth} />
        </svg>
      );
    case "dashed-rect":
      return (
        <svg viewBox="0 0 100 100" {...common} fill="none">
          <rect
            x="2"
            y="2"
            width="96"
            height="96"
            rx="6"
            stroke={stroke}
            strokeWidth={strokeWidth}
            strokeDasharray="6 4"
          />
        </svg>
      );
    case "note":
      // Folded-corner sticky-note silhouette.
      return (
        <svg viewBox="0 0 100 100" {...common} fill="none">
          <path
            d="M2 2 H82 L98 18 V98 H2 Z"
            stroke={stroke}
            strokeWidth={strokeWidth}
          />
          <path
            d="M82 2 V18 H98"
            stroke={stroke}
            strokeWidth={strokeWidth}
          />
        </svg>
      );
    case "fact":
    case "rect":
    default:
      return (
        <svg viewBox="0 0 100 100" {...common} fill="none">
          <rect
            x="2"
            y="2"
            width="96"
            height="96"
            rx="8"
            stroke={stroke}
            strokeWidth={strokeWidth}
          />
        </svg>
      );
  }
}
