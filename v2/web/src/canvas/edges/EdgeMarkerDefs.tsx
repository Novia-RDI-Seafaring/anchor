import { MARKER_IDS } from "./markers";

/**
 * EdgeMarkerDefs — the single SVG `<defs>` block holding every custom
 * `<marker>` glyph used by FloatingEdge / AnchoredEdge.
 *
 * Why one component, mounted once: ReactFlow renders all edges into one
 * outer `<svg>` element, and `<marker>` defs declared anywhere within that
 * SVG are addressable by ID from any edge inside it. So we mount this
 * component as the first child of the edge layer (e.g. as a `<svg>` inside
 * the canvas root) and every edge can reference these IDs.
 *
 * To add a new arrowhead, append a `<marker>` here and a string to
 * `MARKER_IDS` in markers.ts.
 */
export function EdgeMarkerDefs() {
  return (
    <svg
      // Position absolutely, zero-sized, but participates in the SVG defs
      // resolution chain. Keep visible: hidden so it's never painted.
      style={{
        position: "absolute",
        width: 0,
        height: 0,
        overflow: "hidden",
        visibility: "hidden",
      }}
      aria-hidden
    >
      <defs>
        {/* Hollow (unfilled) triangle — UML generalization / SysML subsetting. */}
        <marker
          id={MARKER_IDS.hollowTriangle}
          viewBox="0 0 12 12"
          refX="11"
          refY="6"
          markerWidth="12"
          markerHeight="12"
          orient="auto-start-reverse"
        >
          <path
            d="M 1 1 L 11 6 L 1 11 Z"
            fill="#ffffff"
            stroke="#404040"
            strokeWidth="1.25"
            strokeLinejoin="round"
          />
        </marker>

        {/* Filled diamond — UML composition (whole side). */}
        <marker
          id={MARKER_IDS.filledDiamond}
          viewBox="0 0 14 10"
          refX="1"
          refY="5"
          markerWidth="14"
          markerHeight="10"
          orient="auto-start-reverse"
        >
          <path
            d="M 1 5 L 7 1 L 13 5 L 7 9 Z"
            fill="#404040"
            stroke="#404040"
            strokeWidth="1"
            strokeLinejoin="round"
          />
        </marker>

        {/* Open V-arrow — UML directed association / satisfy / composition part-end. */}
        <marker
          id={MARKER_IDS.openArrow}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="10"
          markerHeight="10"
          orient="auto-start-reverse"
        >
          <path
            d="M 1 1 L 9 5 L 1 9"
            fill="none"
            stroke="#404040"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </marker>

        {/* User-pickable cap markers (Miro-style edge editor). These are
            simpler than the SysML markers — they inherit the edge's stroke
            colour via `currentColor` so a stroke-colour change repaints the
            marker too. The `*-sel` variants are mounted at 20% larger size
            for the selected-edge visual. */}
        {/* Filled arrow at end — default. */}
        <marker
          id={MARKER_IDS.userArrow}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="9"
          markerHeight="9"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
        </marker>
        <marker
          id={MARKER_IDS.userArrowSel}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="11"
          markerHeight="11"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
        </marker>

        {/* Filled circle (dot) — works equally well as a start or end cap. */}
        <marker
          id={MARKER_IDS.userCircle}
          viewBox="0 0 10 10"
          refX="5"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <circle cx="5" cy="5" r="4" fill="currentColor" />
        </marker>
        <marker
          id={MARKER_IDS.userCircleSel}
          viewBox="0 0 10 10"
          refX="5"
          refY="5"
          markerWidth="8.4"
          markerHeight="8.4"
          orient="auto-start-reverse"
        >
          <circle cx="5" cy="5" r="4" fill="currentColor" />
        </marker>
      </defs>
    </svg>
  );
}
