import type { Edge as RfEdge, Node as RfNode } from "@xyflow/react";

import { pickEdgeMode, type HoveredSourceRef } from "@/canvas/edges/edge-mode";
import { provenancePathEdgeIds } from "@/canvas/edges/provenance-path";
import type { CanvasEdge, CanvasNode } from "@/stores/canvasStore";

type Point = { x: number; y: number };

type EdgeProjectionState = {
  hoveredSourceRef: HoveredSourceRef | null;
  hoveredNodeId: string | null;
  selectedEdgeId: string | null;
};

const LAYER_Z_INDEX: Record<NonNullable<CanvasNode["layer"]>, number> = {
  background: -2,
  content: 0,
  annotation: 2,
};

export function ancestorOffset(
  nodeId: string,
  allNodes: Record<string, CanvasNode>,
): Point {
  const offset = { x: 0, y: 0 };
  const visited = new Set<string>();
  let current = allNodes[nodeId]?.parent ?? null;
  while (current != null) {
    if (visited.has(current)) break;
    visited.add(current);
    const parent = allNodes[current];
    if (!parent) break;
    offset.x += parent.x;
    offset.y += parent.y;
    current = parent.parent ?? null;
  }
  return offset;
}

export function canvasNodeSize(node: CanvasNode): {
  width: number | undefined;
  height: number | undefined;
} {
  const data = node.data ?? {};
  return {
    width: node.width ?? (data.width as number | undefined),
    height: node.height ?? (data.height as number | undefined),
  };
}

export function projectCanvasNode(
  node: CanvasNode,
  allNodes: Record<string, CanvasNode>,
): RfNode {
  const isArea = node.node_type === "area";
  const parentExists = node.parent != null && allNodes[node.parent] != null;
  const offset = parentExists ? ancestorOffset(node.id, allNodes) : { x: 0, y: 0 };
  const { width, height } = canvasNodeSize(node);
  const legacyLocked = node.data?.locked === true;
  const locked = node.locked === true || legacyLocked;
  const data = {
    label: node.label,
    ...(node.data ?? {}),
    ...(width !== undefined ? { width } : {}),
    ...(height !== undefined ? { height } : {}),
    locked,
  };
  const layer = node.layer ?? "content";

  return {
    id: node.id,
    position: { x: node.x - offset.x, y: node.y - offset.y },
    data,
    type: node.node_type,
    ...(parentExists
      ? { parentId: node.parent as string, extent: "parent" as const }
      : {}),
    zIndex: isArea && layer === "content" ? -1 : LAYER_Z_INDEX[layer],
    ...(locked ? { draggable: false } : {}),
    hidden: node.visible === false,
    ...(node.opacity == null ? {} : { style: { opacity: node.opacity } }),
  };
}

export function projectCanvasEdges(
  nodes: Record<string, CanvasNode>,
  edges: Record<string, CanvasEdge>,
  state: EdgeProjectionState,
): RfEdge[] {
  const typePicks: Record<string, string> = {};
  const evidenceForDoc: Record<string, string[]> = {};
  let activeEdgeId: string | null = null;

  for (const edge of Object.values(edges)) {
    const target = nodes[edge.target];
    const targetSlug = (target?.data as { slug?: string } | undefined)?.slug;
    const mode = pickEdgeMode(
      {
        edge_type: edge.edge_type,
        sourceHandle: edge.sourceHandle,
        targetHandle: edge.targetHandle,
        data: edge.data as
          | { kind?: string; source_ref?: Record<string, unknown> }
          | undefined,
        targetDocSlug: targetSlug,
      },
      state.hoveredSourceRef,
    );
    typePicks[edge.id] = mode;
    if (edge.data?.kind !== "evidence") continue;
    if (targetSlug) (evidenceForDoc[targetSlug] ??= []).push(edge.id);
    if (mode === "anchored") activeEdgeId = edge.id;
  }

  const dimmedEvidence = new Set<string>();
  if (activeEdgeId && state.hoveredSourceRef?.slug) {
    for (const edgeId of evidenceForDoc[state.hoveredSourceRef.slug] ?? []) {
      if (edgeId !== activeEdgeId) dimmedEvidence.add(edgeId);
    }
  }

  const pathEdges = provenancePathEdgeIds(
    state.hoveredNodeId,
    Object.fromEntries(
      Object.values(nodes).map((node) => [
        node.id,
        { id: node.id, node_type: node.node_type },
      ]),
    ),
    Object.values(edges).map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      data: edge.data as { kind?: string } | undefined,
    })),
  );
  if (pathEdges.size > 0) {
    for (const edge of Object.values(edges)) {
      if (edge.data?.kind === "evidence" && !pathEdges.has(edge.id)) {
        dimmedEvidence.add(edge.id);
      }
    }
  }

  return Object.values(edges).map((edge) => {
    const onPath = pathEdges.has(edge.id);
    const dimmed = dimmedEvidence.has(edge.id) && !onPath;
    const active = activeEdgeId === edge.id || onPath;
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? undefined,
      targetHandle: edge.targetHandle ?? undefined,
      label: edge.label,
      type: typePicks[edge.id] ?? "floating",
      data: {
        ...(edge.data ?? {}),
        label: edge.label || undefined,
        active,
        dimmed,
      },
      style: dimmed ? { opacity: 0.25 } : undefined,
      selected: state.selectedEdgeId === edge.id,
    } satisfies RfEdge;
  });
}
