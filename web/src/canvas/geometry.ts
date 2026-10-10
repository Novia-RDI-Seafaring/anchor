export type GeometryNode = { id: string; x: number; y: number; parent?: string | null };
export type Position = { x: number; y: number };
export type NodeMove = Position & { id: string };
export type DraggedNode = { id: string; position: Position };

export function visibleParentId(nodeId: string, nodes: Record<string, GeometryNode>, hidden?: Set<string>): string | undefined {
  const parent = nodes[nodeId]?.parent;
  return parent && parent !== nodeId && nodes[parent] && !hidden?.has(parent) ? parent : undefined;
}

/** Canonical positions are already absolute, including the immediate parent. */
export function visibleParentOffset(nodeId: string, nodes: Record<string, GeometryNode>, hidden?: Set<string>): Position {
  const parent = visibleParentId(nodeId, nodes, hidden);
  return parent ? { x: nodes[parent]!.x, y: nodes[parent]!.y } : { x: 0, y: 0 };
}

export function absolutePosition(nodeId: string, position: Position, nodes: Record<string, GeometryNode>, hidden?: Set<string>): Position {
  const offset = visibleParentOffset(nodeId, nodes, hidden);
  return { x: position.x + offset.x, y: position.y + offset.y };
}

/** Include canonical children even when folding removes them from ReactFlow. */
export function parentedNodeIds(nodes: Record<string, GeometryNode>, roots: string[]): string[] {
  const children = new Map<string, string[]>();
  for (const node of Object.values(nodes)) {
    if (!node.parent) continue;
    const ids = children.get(node.parent) ?? [];
    ids.push(node.id); children.set(node.parent, ids);
  }
  const moved = new Set(roots.filter((id) => nodes[id]));
  const queue = [...moved];
  for (let at = 0; at < queue.length; at++) {
    for (const id of children.get(queue[at]!) ?? []) {
      if (moved.has(id)) continue;
      moved.add(id); queue.push(id);
    }
  }
  return queue;
}

/** Resolve a complete drag before saving, independent of selected-node order. */
export function planDragMoves(nodes: Record<string, GeometryNode>, dragged: DraggedNode[], hidden?: Set<string>): NodeMove[] {
  const explicit = new Map(dragged.filter((node) => nodes[node.id]).map((node) => [node.id, node.position]));
  const resolved = new Map<string, Position>();
  const resolving = new Set<string>();
  const positionFor = (id: string): Position => {
    const cached = resolved.get(id);
    if (cached) return cached;
    const node = nodes[id]!;
    if (resolving.has(id)) return { x: node.x, y: node.y };
    resolving.add(id);
    const relative = explicit.get(id);
    let position: Position;
    if (relative) {
      const parent = visibleParentId(id, nodes, hidden);
      const offset = parent ? positionFor(parent) : { x: 0, y: 0 };
      position = { x: relative.x + offset.x, y: relative.y + offset.y };
    } else if (node.parent && nodes[node.parent] && node.parent !== id) {
      const parent = nodes[node.parent]!;
      const movedParent = positionFor(parent.id);
      position = { x: node.x + movedParent.x - parent.x, y: node.y + movedParent.y - parent.y };
    } else position = { x: node.x, y: node.y };
    resolving.delete(id); resolved.set(id, position);
    return position;
  };
  return parentedNodeIds(nodes, [...explicit.keys()]).flatMap((id) => {
    const position = positionFor(id);
    const node = nodes[id]!;
    return position.x === node.x && position.y === node.y ? [] : [{ id, ...position }];
  });
}
