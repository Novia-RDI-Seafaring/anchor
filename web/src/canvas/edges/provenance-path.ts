/**
 * provenance-path — pure selector that, given a hovered node, finds the
 * evidence/provenance edges tracing that node back to its source document.
 *
 * Why this exists
 * ---------------
 * When an agent scaffolds a "knowledge tree" about one document, every fact
 * node wires an evidence edge back to the SAME document node. N facts -> 1
 * doc means N edges converge on one point: a dense, unreadable tangle (issue
 * #183, the "yarn ball").
 *
 * The chosen fix (maintainer decision 2026-06-26) is perceptual, not
 * structural: leave the edges, render them quiet by default, and on node
 * hover thicken/highlight only the path from the hovered node to its source.
 * Everything else stays thin. The clutter stops mattering because the
 * relevant provenance path lights up on demand.
 *
 * This module owns the path-walk. It is a pure function over the canvas
 * graph so it is trivially unit-testable and never touches React or the DOM.
 * CanvasGraph feeds the result into the per-edge `active` / `dimmed` flags
 * the existing evidence-edge renderers already understand, so highlighting
 * only changes stroke width / colour / opacity. It never changes an edge's
 * routing, handles, or endpoints — hovering cannot make an edge jump.
 *
 * What counts as a provenance edge
 * --------------------------------
 * An edge with `data.kind === "evidence"` (the same discriminator
 * `isEvidenceEdge` / `pickEdgeMode` use). Evidence edges are directed
 * fact -> source: `source` is the citing node, `target` is the document (or
 * an intermediate node that itself cites the document — an evidence chain).
 *
 * What the walk returns
 * ---------------------
 * The set of evidence-edge ids that lie on the provenance path(s) connecting
 * the hovered node to a source document:
 *
 *   - Hovering a FACT node: follow outgoing evidence edges toward the doc,
 *     chaining through any intermediate nodes (fact -> intermediate -> doc),
 *     so the whole chain lights up — not just the first hop.
 *   - Hovering a DOCUMENT (source) node: follow incoming evidence edges
 *     backward to every fact that cites it, so hovering the shared source
 *     lights up all of its provenance fan-in.
 *   - Hovering an INTERMEDIATE node on a chain: light up both directions —
 *     forward to the doc and backward to the facts that route through it.
 *
 * The traversal is direction-aware but cycle-safe (a visited set guards
 * against malformed graphs), and it only ever walks evidence edges, so a
 * node's unrelated plain edges are never highlighted.
 */

export type ProvenanceNode = {
  id: string;
  node_type: string;
};

export type ProvenanceEdge = {
  id: string;
  source: string;
  target: string;
  data?: { kind?: string } & Record<string, unknown>;
};

function isEvidence(edge: ProvenanceEdge): boolean {
  return edge.data?.kind === "evidence";
}

/**
 * Compute the evidence edges on the provenance path from `hoveredNodeId` to
 * its source document(s).
 *
 * Returns an empty set when nothing is hovered, the hovered node is unknown,
 * or the hovered node touches no evidence edges. The caller treats a
 * non-empty result as "highlight these, dim the other evidence edges".
 *
 * The walk is a breadth-first traversal over evidence edges only. From the
 * hovered node we explore:
 *
 *   - forward  (source -> target): toward the document, following chains
 *     (fact -> intermediate -> doc) so the whole path lights up.
 *   - backward (target -> source): the citers that route INTO the hovered
 *     node. So hovering a shared document lights its whole fan-in, and
 *     hovering an intermediate hub lights both its forward path to the doc
 *     and the facts feeding it.
 *
 * Backward traversal is gated to the hovered node itself: forward-reached
 * nodes never spread backward. This keeps the common case ("N facts -> one
 * doc") crisp — hovering a single fact lights only its own edge to the
 * source, never the sibling facts that happen to share that document.
 * Forward traversal is always allowed because following a fact toward its
 * source is the core intent. A `seen` set keeps the walk cycle-safe on
 * malformed graphs.
 */
export function provenancePathEdgeIds(
  hoveredNodeId: string | null | undefined,
  nodes: Record<string, ProvenanceNode>,
  edges: ProvenanceEdge[],
): Set<string> {
  const result = new Set<string>();
  if (!hoveredNodeId) return result;
  if (!nodes[hoveredNodeId]) return result;

  // Adjacency over evidence edges only, kept directed so we can walk
  // forward (toward source) and backward (toward facts) independently.
  const outgoing = new Map<string, ProvenanceEdge[]>(); // source -> edges
  const incoming = new Map<string, ProvenanceEdge[]>(); // target -> edges
  for (const e of edges) {
    if (!isEvidence(e)) continue;
    (outgoing.get(e.source) ?? outgoing.set(e.source, []).get(e.source)!).push(e);
    (incoming.get(e.target) ?? incoming.set(e.target, []).get(e.target)!).push(e);
  }

  // Queue carries the node id plus a `arrivedBackward` gate. The hovered
  // node is the focus: light its forward path toward the source AND its
  // backward fan-in (the citers feeding it). Forward-reached nodes do NOT
  // inherit backward permission, so hovering one fact never spills through a
  // shared document into sibling facts.
  type Visit = { id: string; arrivedBackward: boolean };
  const queue: Visit[] = [{ id: hoveredNodeId, arrivedBackward: true }];
  const seen = new Set<string>([hoveredNodeId]);

  while (queue.length) {
    const { id, arrivedBackward } = queue.shift()!;

    // Forward: follow this node's outgoing evidence edges toward the source.
    for (const e of outgoing.get(id) ?? []) {
      result.add(e.id);
      if (!seen.has(e.target)) {
        seen.add(e.target);
        // Stepping into a node from its fact-facing side: keep walking
        // forward toward the doc, but never spill backward. Arriving AT a
        // document via a fact hover must not fan out to the doc's other
        // citers (that would light every sibling fact that shares the
        // source). Backward fan-in is reserved for a hovered document /
        // hovered intermediate, handled by the start node's permission.
        queue.push({ id: e.target, arrivedBackward: false });
      }
    }

    // Backward: follow incoming evidence edges back toward the citers. Only
    // permitted from the hovered node (or a node already reached backward),
    // so a single fact hover doesn't light its sibling facts via the doc.
    if (arrivedBackward) {
      for (const e of incoming.get(id) ?? []) {
        result.add(e.id);
        if (!seen.has(e.source)) {
          seen.add(e.source);
          queue.push({ id: e.source, arrivedBackward: true });
        }
      }
    }
  }

  return result;
}
