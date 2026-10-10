type LayerNode = {
  node_type: string;
  parent?: string | null;
  layer?: "background" | "content" | "annotation";
};

export const CANVAS_EDGE_Z_INDEX = 0;

/** Order nested backgrounds, edges, cards and annotations without overlap. */
export function canvasNodeLayers(nodes: Record<string, LayerNode>): Record<string, number> {
  const count = Object.keys(nodes).length;
  const layers: Record<string, number> = {};
  for (const [id, node] of Object.entries(nodes)) {
    const seen = new Set([id]);
    let parent = node.parent;
    let depth = 0;
    while (parent && nodes[parent] && !seen.has(parent)) {
      seen.add(parent);
      depth += 1;
      parent = nodes[parent]?.parent;
    }
    layers[id] = node.node_type === "area" || node.layer === "background"
      ? depth - count
      : node.layer === "annotation" ? count + depth + 1 : depth + 1;
  }
  return layers;
}
