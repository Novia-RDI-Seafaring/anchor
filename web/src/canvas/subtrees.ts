/** Direction and deterministic, cycle-safe BFS match core/workspace/layout.py. */
export type SubtreeDirection = "outgoing" | "incoming" | "any";
export type StructureNode = {
  id: string;
  node_type: string;
  parent?: string | null;
  data?: Record<string, unknown>;
};
export type StructureEdge = {
  source: string;
  target: string;
  data?: Record<string, unknown>;
};

export function subtreeAdjacency(edges: StructureEdge[], direction: SubtreeDirection) {
  const adjacency = new Map<string, Set<string>>();
  const add = (from: string, to: string) => {
    if (!adjacency.has(from)) adjacency.set(from, new Set());
    adjacency.get(from)!.add(to);
  };
  for (const edge of edges) {
    if (direction !== "incoming") add(edge.source, edge.target);
    if (direction !== "outgoing") add(edge.target, edge.source);
  }
  return adjacency;
}

export function walkSubtree(root: string, adjacency: Map<string, Set<string>>, stop?: Set<string>) {
  const visited = new Set([root]);
  const queue = [root];
  for (let i = 0; i < queue.length; i++) {
    const current = queue[i]!;
    if (stop?.has(current)) continue;
    for (const child of [...(adjacency.get(current) ?? [])].sort()) {
      if (visited.has(child)) continue;
      visited.add(child);
      queue.push(child);
    }
  }
  visited.delete(root);
  return visited;
}

export function collapseDirection(node: StructureNode): SubtreeDirection {
  const value = node.data?.collapse_direction;
  return value === "incoming" || value === "any" ? value : "outgoing";
}

/** Position, label and body updates do not change the fold projection. */
export function structureSignature(nodes: Record<string, StructureNode>, edges: StructureEdge[]) {
  return JSON.stringify([
    Object.values(nodes).map((node) => [node.id, node.node_type, node.parent, node.data?.collapsed === true, collapseDirection(node)]),
    edges.map((edge) => [edge.source, edge.target, edge.data?.kind === "evidence"]),
  ]);
}

/** A projection only: the canonical nodes, edges and positions stay intact. */
export function foldedGraph(nodes: Record<string, StructureNode>, edges: StructureEdge[]) {
  const structural = edges.filter((edge) => edge.data?.kind !== "evidence"
    && nodes[edge.source] && nodes[edge.target]);
  for (const node of Object.values(nodes)) {
    if (node.parent && nodes[node.parent]) structural.push({ source: node.parent, target: node.id });
  }
  const descendants = new Map<string, Set<string>>();
  const adjacencyByRoot = new Map<string, Map<string, Set<string>>>();
  const adjacencies = {
    outgoing: subtreeAdjacency(structural, "outgoing"),
    incoming: subtreeAdjacency(structural, "incoming"),
    any: subtreeAdjacency(structural, "any"),
  };
  for (const node of Object.values(nodes)) {
    const direction = collapseDirection(node);
    let adjacency = adjacencies[direction];
    // A source card is a natural root for its evidence dependents. Evidence
    // must never make the source document a child of a claim.
    if (node.node_type === "document") {
      adjacency = new Map(adjacency);
      adjacency.set(node.id, new Set(adjacency.get(node.id)));
      for (const edge of edges) {
        if (edge.data?.kind !== "evidence" || edge.target !== node.id || !nodes[edge.source]) continue;
        if (!adjacency.has(node.id)) adjacency.set(node.id, new Set());
        adjacency.get(node.id)!.add(edge.source);
      }
    }
    adjacencyByRoot.set(node.id, adjacency);
    descendants.set(node.id, walkSubtree(node.id, adjacency));
  }
  const collapsed = Object.values(nodes).filter((node) => node.data?.collapsed === true).map((node) => node.id).sort();
  const hidden = new Set(collapsed.flatMap((id) => [...descendants.get(id)!]));
  // An ancestor may hide a nested folded root. In a cycle, keep the first
  // folded root visible so the component always has an expand affordance.
  for (const root of collapsed) {
    const dominated = collapsed.some((other) => other !== root && descendants.get(other)!.has(root)
      && (!descendants.get(root)!.has(other) || other < root));
    if (!dominated) hidden.delete(root);
  }
  // Rescue shared descendants reached through a visible expanded parent.
  // Iterate because rescuing one shared branch may expose another parent.
  let changed = true;
  const stops = new Set(collapsed);
  while (changed) {
    changed = false;
    for (const root of collapsed) {
      const candidates = descendants.get(root)!;
      const adjacency = adjacencyByRoot.get(root)!;
      for (const [parent, children] of adjacency) {
        if (parent === root || candidates.has(parent) || hidden.has(parent) || stops.has(parent)) continue;
        for (const child of children) {
          if (!candidates.has(child)) continue;
          const rescued = new Set([child, ...walkSubtree(child, adjacency, stops)]);
          for (const id of rescued) if (hidden.delete(id)) changed = true;
        }
      }
    }
  }
  return { hidden, descendants };
}

export const COMPACT_CARD_TYPES = new Set(["fact", "note", "markdown", "spec"]);
export function compactDisplay(nodeType: string, data: Record<string, unknown>) {
  return COMPACT_CARD_TYPES.has(nodeType) && data.display_mode !== "full";
}

export function cardSummary(data: Record<string, unknown>) {
  for (const key of ["subtitle", "text", "description"]) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) return value.trim().split(/\r?\n/, 1)[0];
  }
  return Array.isArray(data.rows) ? `${data.rows.length} rows` : "";
}
