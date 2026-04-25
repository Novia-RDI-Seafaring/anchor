import type React from "react";

import type { Edge, Node } from "@xyflow/react";

import type { KBDocument } from "@/contexts/AppContext";

import type { CanvasItem } from "./canvas-model";
import type { Relation } from "./canvasGraphUtils";

export type CollapsibleNodeType = "concept" | "entity" | "category" | "topic";
export type FlowPosition = { x: number; y: number };

export const COLOR_HEX: Record<string, string> = {
  violet: "#8b5cf6",
  blue: "#3b82f6",
  emerald: "#10b981",
  amber: "#f59e0b",
  rose: "#f43f5e",
  indigo: "#6366f1",
  slate: "#64748b",
};

export function connectedComponents(nodes: Node[], edges: Edge[]): string[][] {
  const visibleIds = new Set(nodes.filter((node) => !node.hidden).map((node) => node.id));
  const neighbors = new Map<string, Set<string>>();

  for (const id of visibleIds) neighbors.set(id, new Set());

  for (const edge of edges) {
    if (edge.hidden || !visibleIds.has(edge.source) || !visibleIds.has(edge.target)) continue;
    neighbors.get(edge.source)?.add(edge.target);
    neighbors.get(edge.target)?.add(edge.source);
  }

  const visited = new Set<string>();
  const components: string[][] = [];

  for (const node of nodes) {
    if (node.hidden || visited.has(node.id)) continue;
    const component: string[] = [];
    const queue = [node.id];
    visited.add(node.id);

    while (queue.length) {
      const current = queue.shift()!;
      component.push(current);
      for (const next of neighbors.get(current) ?? []) {
        if (visited.has(next)) continue;
        visited.add(next);
        queue.push(next);
      }
    }

    components.push(component);
  }

  return components;
}

export function applyMindmapLayout(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes;

  const childrenOf = new Map<string, string[]>();
  const hasParent = new Set<string>();
  for (const edge of edges) {
    if (edge.hidden || edge.target.startsWith("__doc_")) continue;
    const children = childrenOf.get(edge.source) ?? [];
    children.push(edge.target);
    childrenOf.set(edge.source, children);
    hasParent.add(edge.target);
  }

  const visibleIds = new Set(nodes.filter((node) => !node.hidden).map((node) => node.id));
  const roots = nodes.filter((node) => !node.hidden && !node.id.startsWith("__doc_") && !hasParent.has(node.id));

  const positions = new Map<string, { x: number; y: number }>();
  const topicRadius = 380;
  const leafRadius = 310;
  const clusterWidth = 1150;

  roots.forEach((root, rootIndex) => {
    const centerX = rootIndex * clusterWidth;
    positions.set(root.id, { x: centerX, y: 0 });

    const topics = (childrenOf.get(root.id) ?? []).filter((id) => visibleIds.has(id));
    const topicCount = topics.length;

    topics.forEach((topicId, index) => {
      const angle =
        topicCount <= 1 ? -Math.PI / 2 : -Math.PI / 2 + (2 * Math.PI * index) / topicCount;
      const topicX = centerX + topicRadius * Math.cos(angle);
      const topicY = topicRadius * Math.sin(angle);
      positions.set(topicId, { x: topicX, y: topicY });

      const leaves = (childrenOf.get(topicId) ?? []).filter((id) => visibleIds.has(id));
      const leafCount = leaves.length;
      leaves.forEach((leafId, leafIndex) => {
        const spread = Math.PI / (leafCount <= 1 ? 1 : 2.2);
        const leafAngle =
          leafCount <= 1 ? angle : angle - spread / 2 + (spread * leafIndex) / (leafCount - 1);
        positions.set(leafId, {
          x: topicX + leafRadius * Math.cos(leafAngle),
          y: topicY + leafRadius * Math.sin(leafAngle),
        });
      });
    });
  });

  const docNodes = nodes.filter((node) => !node.hidden && node.id.startsWith("__doc_"));
  const docSpacing = 230;
  const totalDocWidth = (docNodes.length - 1) * docSpacing;
  const docCenterX = roots.length > 0 ? roots.reduce((sum, _, index) => sum + index * clusterWidth, 0) / roots.length : 0;
  docNodes.forEach((docNode, index) => {
    positions.set(docNode.id, { x: docCenterX - totalDocWidth / 2 + index * docSpacing, y: -360 });
  });

  let fallbackX = 0;
  for (const node of nodes) {
    if (node.hidden || positions.has(node.id)) continue;
    positions.set(node.id, { x: fallbackX, y: 800 });
    fallbackX += 280;
  }

  return nodes.map((node) => (node.hidden || !positions.has(node.id) ? node : { ...node, position: positions.get(node.id)! }));
}

export function placeNodesManually(
  nodes: Node[],
  relationParentOf: Map<string, string>,
  overrides: Record<string, FlowPosition>,
  existingPositions: Map<string, FlowPosition>,
): Node[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const relationChildren = new Map<string, string[]>();
  for (const [childId, parentId] of relationParentOf.entries()) {
    const children = relationChildren.get(parentId) ?? [];
    children.push(childId);
    relationChildren.set(parentId, children);
  }

  const positioned = new Map<string, FlowPosition>();

  const resolve = (nodeId: string, lineage = new Set<string>()): FlowPosition => {
    const cached = positioned.get(nodeId);
    if (cached) return cached;

    const saved = overrides[nodeId];
    if (saved) {
      positioned.set(nodeId, saved);
      return saved;
    }

    const existing = existingPositions.get(nodeId);
    if (existing) {
      positioned.set(nodeId, existing);
      return existing;
    }

    const node = nodeById.get(nodeId);
    const nodeIndex = nodes.findIndex((item) => item.id === nodeId);

    if (node?.parentId) {
      const siblings = nodes.filter((item) => item.parentId === node.parentId);
      const siblingIndex = Math.max(0, siblings.findIndex((item) => item.id === nodeId));
      const position = {
        x: 40 + (siblingIndex % 2) * 220,
        y: 56 + Math.floor(siblingIndex / 2) * 120,
      };
      positioned.set(nodeId, position);
      return position;
    }

    const relationParentId = relationParentOf.get(nodeId);
    if (relationParentId && !lineage.has(nodeId)) {
      const nextLineage = new Set(lineage);
      nextLineage.add(nodeId);
      const parentPosition = resolve(relationParentId, nextLineage);
      const siblings = relationChildren.get(relationParentId) ?? [];
      const siblingIndex = Math.max(0, siblings.indexOf(nodeId));
      const spread = siblings.length <= 1 ? 0 : (siblingIndex - (siblings.length - 1) / 2) * 120;
      const position = {
        x: parentPosition.x + 280,
        y: parentPosition.y + spread,
      };
      positioned.set(nodeId, position);
      return position;
    }

    const position = {
      x: (nodeIndex % 4) * 320,
      y: 120 + Math.floor(nodeIndex / 4) * 180,
    };
    positioned.set(nodeId, position);
    return position;
  };

  return nodes.map((node) => ({ ...node, position: resolve(node.id) }));
}

export function descendants(rootIds: string[], childrenOf: Map<string, string[]>): Set<string> {
  const hidden = new Set<string>();
  const queue = [...rootIds];
  while (queue.length) {
    const current = queue.shift()!;
    for (const child of childrenOf.get(current) ?? []) {
      if (!hidden.has(child)) {
        hidden.add(child);
        queue.push(child);
      }
    }
  }
  return hidden;
}

export function nodeStyle(color?: string): React.CSSProperties | undefined {
  if (!color || !COLOR_HEX[color]) return undefined;
  return { boxShadow: `0 0 0 2.5px ${COLOR_HEX[color]}, 0 2px 8px rgba(0,0,0,0.08)`, borderRadius: 12 };
}

export const COLLAPSIBLE_NODE_COMPONENTS: Record<CollapsibleNodeType, string> = {
  concept: "conceptNode",
  entity: "entityNode",
  category: "categoryNode",
  topic: "topicNode",
};

export function isCollapsibleNodeType(nodeType: CanvasItem["semanticType"]): nodeType is CollapsibleNodeType {
  return nodeType === "concept" || nodeType === "entity" || nodeType === "category" || nodeType === "topic";
}

export function buildFlowNode(
  id: string,
  type: string,
  color: string | undefined,
  hidden: boolean,
  data: Record<string, unknown>,
): Node {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    hidden,
    style: nodeStyle(color),
    data,
  };
}

export function applyExplicitNodeSize(node: CanvasItem, rfNode: Node, fallback: { w: number; h: number }): Node {
  const width = node.width && node.width > 0 ? node.width : fallback.w;
  const height = node.height && node.height > 0 ? node.height : fallback.h;
  return {
    ...rfNode,
    style: {
      ...rfNode.style,
      width,
      height,
    },
  };
}

export function buildCollapsibleNodeData(
  node: CanvasItem,
  childrenOf: Map<string, string[]>,
  collapsedIds: Set<string>,
  onToggleCollapse: (id: string) => void,
  onDelete?: (id: string) => void,
  onSetColor?: (id: string, color: string) => void,
) {
  return {
    node,
    childCount: descendants([node.id], childrenOf).size,
    collapsed: collapsedIds.has(node.id),
    onToggleCollapse,
    onDelete,
    onSetColor,
  };
}

export function getEvidenceData(
  nodeId: string,
  relations: Relation[],
  documents: KBDocument[],
) {
  const relation = relations.find((item) => item.from_id === nodeId && item.to_id.startsWith("__doc_"));
  const documentId = relation?.document_id || relation?.to_id.replace(/^__doc_/, "");
  const document = documentId ? documents.find((item) => item.document_id === documentId) : undefined;
  return {
    evidenceFilename: document?.filename,
    evidencePage: relation?.page,
    evidenceHighlights: relation?.highlights,
  };
}
