import type { useCanvasStore } from "@/stores/canvasStore";

type State = ReturnType<typeof useCanvasStore.getState>;
export type ClipboardNode = State["nodes"][string];
export type ClipboardEdge = State["edges"][string];
export type CanvasFragment = { canvas: string; nodes: ClipboardNode[]; edges: ClipboardEdge[] };

/** Citations are reusable; judgements about an earlier object are not. */
export function copyData(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(copyData);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).filter(([key]) =>
    !["review", "evidence", "revalidate_evidence"].includes(key),
  ).map(([key, item]) => [key, key === "source_ref" ? structuredClone(item) : copyData(item)]));
}

export function captureCanvas(state: Pick<State, "nodes" | "edges">, canvas: string, nodeIds: string[], edgeIds: string[] = []): CanvasFragment {
  const chosen = new Set(nodeIds.filter((id) => state.nodes[id]));
  // A container and its contents move together, including nested containers.
  let grew = true;
  while (grew) {
    grew = false;
    for (const node of Object.values(state.nodes)) {
      if (node.parent && chosen.has(node.parent) && !chosen.has(node.id)) {
        chosen.add(node.id); grew = true;
      }
    }
  }
  return structuredClone({ canvas, nodes: orderCanvasNodes(Object.values(state.nodes).filter((n) => chosen.has(n.id))),
    edges: Object.values(state.edges).filter((e) => edgeIds.includes(e.id) || (chosen.has(e.source) && chosen.has(e.target))) });
}

export function planCanvasPaste(fragment: CanvasFragment, destination: string, existing: Set<string>, offset: { x: number; y: number }, freshId: () => string = () => crypto.randomUUID()): CanvasFragment {
  const ids = new Map(fragment.nodes.map((n) => [n.id, freshId()]));
  const nodes = fragment.nodes.map((n) => ({ ...structuredClone(n), id: ids.get(n.id)!, x: n.x + offset.x, y: n.y + offset.y,
    parent: n.parent ? ids.get(n.parent) ?? (fragment.canvas === destination && existing.has(n.parent) ? n.parent : null) : null,
    data: copyData(n.data ?? {}) as Record<string, unknown> }));
  const edges = fragment.edges.map((e) => {
    const endpoint = (id: string) => ids.get(id) ?? (fragment.canvas === destination && existing.has(id) ? id : null);
    const source = endpoint(e.source), target = endpoint(e.target);
    if (!source || !target) throw new Error("Copy both endpoints to paste this connector on another canvas.");
    return { ...structuredClone(e), id: freshId(), source, target, data: copyData(e.data ?? {}) as Record<string, unknown> };
  });
  return { canvas: destination, nodes: orderCanvasNodes(nodes), edges };
}

/** Create parents first; deleting in reverse also avoids cascaded child deletes. */
function orderCanvasNodes(nodes: ClipboardNode[]): ClipboardNode[] {
  const ordered: ClipboardNode[] = [];
  const pending = [...nodes];
  while (pending.length) {
    const at = pending.findIndex((n) => !n.parent || !pending.some((p) => p.id === n.parent));
    if (at < 0) throw new Error("Cannot copy a cyclic container hierarchy.");
    ordered.push(...pending.splice(at, 1));
  }
  return ordered;
}
