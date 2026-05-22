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
 *   - "anchored": edge is evidence AND the hovered source_ref matches this
 *      edge's stored source_ref (same slug + page; same region_id if both
 *      sides know it). Edge will use its sourceHandle/targetHandle.
 *   - "floating": everything else, including evidence edges with no active
 *      hover match. The node-to-node centroid renderer is the rest state.
 */
export function pickEdgeMode(
  edge: EdgeForMode,
  hovered: HoveredSourceRef,
): "anchored" | "floating" {
  // Non-evidence anchored edges (e.g. SysML port-to-port) keep their type.
  const kind = edge.data?.kind;
  if (kind !== "evidence") {
    return edge.edge_type === "anchored" ? "anchored" : "floating";
  }
  // Evidence edges with no hover context always float.
  if (!hovered) return "floating";
  const ref = edge.data?.source_ref;
  if (!ref) return "floating";
  // Slug must match the document on the target end.
  if (edge.targetDocSlug && hovered.slug !== edge.targetDocSlug) return "floating";
  if (ref.page !== undefined && hovered.page !== ref.page) return "floating";
  // If BOTH sides claim a region_id and they disagree → no match. If either
  // side omits region_id, the page-level match is sufficient (table-row
  // hover broadcasts region_id, but bare doc-page hover may not).
  if (
    ref.region_id !== undefined
    && hovered.region_id !== undefined
    && ref.region_id !== hovered.region_id
  ) return "floating";
  return "anchored";
}
