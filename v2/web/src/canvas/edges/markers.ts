/**
 * SysML/UML edge-marker dispatch.
 *
 * The backend's anchor_sysml extension stamps `data.marker` on every edge
 * it emits. The canvas renders a custom edge component (`FloatingEdge` /
 * `AnchoredEdge`) that consults this dispatcher to pick:
 *
 *   - `markerStartId` / `markerEndId` — IDs of `<marker>` elements rendered
 *     once near the canvas root (see `EdgeMarkerDefs`).
 *   - `strokeDasharray`           — solid vs dashed line.
 *   - `labelOverride`             — optional inline label (e.g. `«satisfy»`).
 *
 * Adding a new marker is a four-step seam:
 *   1. Append the marker name to `EdgeMarker`.
 *   2. Add a row to `MARKER_DISPATCH`.
 *   3. If a new arrowhead glyph is needed, add a `<marker>` to
 *      `EdgeMarkerDefs` and reference its ID from your dispatch row.
 *   4. (Optional) Add a unit test in `markers.test.ts` for the new row.
 *
 * No conditionals scattered across the edge component — everything runs
 * through this map.
 */

export type EdgeMarker =
  | "inheritance"
  | "redefinition"
  | "subset"
  | "composition"
  | "interface-connection"
  | "satisfy"
  | "subject"
  | "association";

export type MarkerStyle = {
  /** SVG marker ID rendered at the source end (or null). */
  markerStartId: string | null;
  /** SVG marker ID rendered at the target end (or null). */
  markerEndId: string | null;
  /** SVG `stroke-dasharray` string; empty = solid. */
  strokeDasharray: string;
  /** Optional inline label appended to or replacing the user label. */
  labelOverride: string | null;
};

// IDs of the SVG <marker> defs in `EdgeMarkerDefs.tsx`. Strings are kept in
// sync with that file; if you rename one there, rename it here.
//
// `user*` ids belong to the Miro-style edge editor — they're the start/end
// cap glyphs the user can pick from the EdgeContextToolbar. The `*-sel`
// variants are slightly larger and used when the edge is selected.
export const MARKER_IDS = {
  hollowTriangle: "anchor-mk-hollow-triangle",
  filledDiamond: "anchor-mk-filled-diamond",
  openArrow: "anchor-mk-open-arrow",
  userArrow: "anchor-mk-user-arrow",
  userArrowSel: "anchor-mk-user-arrow-sel",
  userCircle: "anchor-mk-user-circle",
  userCircleSel: "anchor-mk-user-circle-sel",
} as const;

const SOLID = "";
const DASHED = "6 4";

/**
 * Wire-table for marker → visual style. Order matters only for readability.
 */
const MARKER_DISPATCH: Record<EdgeMarker, MarkerStyle> = {
  // UML generalization: hollow triangle pointing at the parent type.
  inheritance: {
    markerStartId: null,
    markerEndId: MARKER_IDS.hollowTriangle,
    strokeDasharray: SOLID,
    labelOverride: null,
  },
  // SysML redefinition: solid line + hollow triangle, tagged ":>>".
  redefinition: {
    markerStartId: null,
    markerEndId: MARKER_IDS.hollowTriangle,
    strokeDasharray: SOLID,
    labelOverride: ":>>",
  },
  // SysML subsetting: dashed line + hollow triangle.
  subset: {
    markerStartId: null,
    markerEndId: MARKER_IDS.hollowTriangle,
    strokeDasharray: DASHED,
    labelOverride: null,
  },
  // UML composition: filled diamond at the WHOLE (source) + open arrow at the PART.
  composition: {
    markerStartId: MARKER_IDS.filledDiamond,
    markerEndId: MARKER_IDS.openArrow,
    strokeDasharray: SOLID,
    labelOverride: null,
  },
  // SysML interface (port) connection: plain solid line, no arrowhead.
  "interface-connection": {
    markerStartId: null,
    markerEndId: null,
    strokeDasharray: SOLID,
    labelOverride: null,
  },
  // SysML satisfy: dashed line, open arrow at the requirement (target),
  // tagged with the «satisfy» stereotype.
  satisfy: {
    markerStartId: null,
    markerEndId: MARKER_IDS.openArrow,
    strokeDasharray: DASHED,
    labelOverride: "«satisfy»",
  },
  // SysML subject: plain solid line, no arrowhead.
  subject: {
    markerStartId: null,
    markerEndId: null,
    strokeDasharray: SOLID,
    labelOverride: null,
  },
  // Generic association: solid line, open arrow at target. Default fallback.
  association: {
    markerStartId: null,
    markerEndId: MARKER_IDS.openArrow,
    strokeDasharray: SOLID,
    labelOverride: null,
  },
};

const DEFAULT_STYLE: MarkerStyle = MARKER_DISPATCH.association;

/**
 * Resolve a marker name → visual style. Unknown markers fall back to
 * `association` so the edge always renders something sensible.
 */
export function arrowheadFor(marker: string | null | undefined): MarkerStyle {
  if (!marker) return DEFAULT_STYLE;
  const found = (MARKER_DISPATCH as Record<string, MarkerStyle>)[marker];
  return found ?? DEFAULT_STYLE;
}

/**
 * Build the `markerStart`/`markerEnd` URL fragments ReactFlow expects.
 * Returns `undefined` when the style asks for no marker on that end so the
 * SVG attribute is omitted entirely.
 */
export function markerUrls(style: MarkerStyle): {
  markerStart: string | undefined;
  markerEnd: string | undefined;
} {
  return {
    markerStart: style.markerStartId ? `url(#${style.markerStartId})` : undefined,
    markerEnd: style.markerEndId ? `url(#${style.markerEndId})` : undefined,
  };
}
