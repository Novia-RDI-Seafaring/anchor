/**
 * Edge-mode selector — pure function deciding whether an evidence edge
 * renders as `floating` (node-to-node centroid) or `anchored` (pinned to
 * specific row/region handles).
 *
 * The rule is hover-driven: an evidence edge ONLY anchors while the
 * hoveredSourceRef "matches" the edge's stored `data.source_ref`. The rest
 * of the time it floats so the graph stays loose and readable. Matching is
 * `slug + page + region_id` — bbox is intentionally ignored because we want
 * a row hover (which broadcasts only page+region_id) to still light up the
 * edge, and a region hover that knows the bbox to still light up the row.
 *
 * Non-evidence edges always keep their declared `edge_type`; they never
 * swap modes on hover.
 */
export type EdgeSourceRef = {
  page?: number;
  region_id?: string;
  bbox?: number[];
};

export type HoveredSourceRef = {
  slug: string;
  page: number;
  region_id?: string;
  bbox?: number[];
} | null;

export type EdgeForMode = {
  /** What the backend persisted: usually "anchored" for evidence edges,
   *  "floating" for loose graph edges, or any custom string. */
  edge_type: string;
  data?: { kind?: string; source_ref?: EdgeSourceRef } | undefined;
  /** Slug of the document node this edge targets. The caller resolves it
   *  from the canvas store before calling pickEdgeMode. */
  targetDocSlug?: string | undefined;
};

/**
 * Decide what ReactFlow `type` an edge should use right now.
 *
 * Return value is the literal `edge_type` string ReactFlow's `edgeTypes`
 * map resolves to a renderer. The Miro-style edge editor lets a user pick
 * any of `floating`, `anchored`, `smooth`, `step`, `straight`, so the
 * function must preserve user picks for non-evidence edges AND fall back
 * to user picks for evidence edges that aren't currently hover-matched.
 *
 * Behaviour:
 *
 *   - Non-evidence: return the stored `edge_type` unchanged. Any of the
 *     five routers is fine; we just hand it back so ReactFlow renders
 *     with the matching component. (Pre-feature: anchored/floating only;
 *     unknown values would default-fall-through. We keep that fallback
 *     for unknown values so the previous test cases still pass.)
 *
 *   - Evidence: when the hover broadcasts a source_ref that matches the
 *     edge's stored source_ref (slug + page; region_id if both sides
 *     know it), flip to `anchored` so the row-handle → region-handle
 *     wiring shows. Otherwise return the stored `edge_type` — i.e. the
 *     user's chosen routing for that edge (smooth/step/straight all
 *     preserved). This is what lets a user pick "Route → smooth" on an
 *     evidence edge without losing the row-handle swap on hover.
 */
export type EdgeRouteType = "floating" | "anchored" | "smooth" | "step" | "straight";

const KNOWN_TYPES = new Set<EdgeRouteType>(["floating", "anchored", "smooth", "step", "straight"]);

function asKnownType(t: string): EdgeRouteType {
  return (KNOWN_TYPES.has(t as EdgeRouteType) ? (t as EdgeRouteType) : "floating");
}

/**
 * Rest-state mapping for an evidence edge that isn't currently hover-matched.
 *
 *   - stored `anchored` → render as `floating` (legacy: evidence edges
 *     persist as anchored but visually float when not hovered).
 *   - stored `smooth` / `step` / `straight` / `floating` → preserve the
 *     user's chosen routing. This is what lets the Miro-style picker
 *     change the route on an evidence edge without losing the
 *     row→region hover swap.
 */
function evidenceRestState(stored: EdgeRouteType): EdgeRouteType {
  return stored === "anchored" ? "floating" : stored;
}

export function pickEdgeMode(
  edge: EdgeForMode,
  hovered: HoveredSourceRef,
): EdgeRouteType {
  const stored = asKnownType(edge.edge_type);
  // Non-evidence anchored edges (e.g. SysML port-to-port) keep their type.
  const kind = edge.data?.kind;
  if (kind !== "evidence") return stored;
  // Evidence edges with no hover context fall back to the rest state.
  if (!hovered) return evidenceRestState(stored);
  const ref = edge.data?.source_ref;
  if (!ref) return evidenceRestState(stored);
  // Slug must match the document on the target end.
  if (edge.targetDocSlug && hovered.slug !== edge.targetDocSlug) return evidenceRestState(stored);
  if (ref.page !== undefined && hovered.page !== ref.page) return evidenceRestState(stored);
  // If BOTH sides claim a region_id and they disagree → no match.
  if (
    ref.region_id !== undefined
    && hovered.region_id !== undefined
    && ref.region_id !== hovered.region_id
  ) return evidenceRestState(stored);
  return "anchored";
}
