"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import { Network } from "lucide-react";
import {
  EntityNode,
  CategoryNode,
  TopicNode,
  FactNode,
  SourceNode,
  SpecNode,
  type CanvasNodeData,
} from "./KnowledgeNodes";
import { PDFModal, type PDFHighlight } from "./PDFModal";

// --- Types ---
interface Relation {
  from_id: string;
  to_id: string;
  label: string;
}

interface CanvasState {
  nodes: CanvasNodeData[];
  relations: Relation[];
}

interface PDFModalState {
  filename: string;
  page: number;
  highlights: PDFHighlight[];
}

// --- Node sizes (width × height in px) used by dagre for spacing ---
const NODE_SIZE: Record<string, { w: number; h: number }> = {
  entityNode:   { w: 280, h: 70  },
  categoryNode: { w: 220, h: 55  },
  topicNode:    { w: 240, h: 60  },
  factNode:     { w: 280, h: 100 },
  sourceNode:   { w: 180, h: 40  },
  specNode:     { w: 260, h: 130 },
};
const DEFAULT_SIZE = { w: 220, h: 80 };

function connectedComponents(nodes: Node[], edges: Edge[]): string[][] {
  const visibleIds = new Set(nodes.filter((node) => !node.hidden).map((node) => node.id));
  const neighbors = new Map<string, Set<string>>();

  for (const id of visibleIds) {
    neighbors.set(id, new Set());
  }

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

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes;

  const positions = new Map<string, { x: number; y: number }>();
  const components = connectedComponents(nodes, edges);
  let yOffset = 0;
  const componentGap = 120;

  for (const component of components) {
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: "TB", nodesep: 50, ranksep: 80, edgesep: 10 });

    for (const nodeId of component) {
      const node = nodes.find((item) => item.id === nodeId);
      if (!node || node.hidden) continue;
      const sz = NODE_SIZE[node.type ?? ""] ?? DEFAULT_SIZE;
      g.setNode(node.id, { width: sz.w, height: sz.h });
    }

    for (const edge of edges) {
      if (edge.hidden) continue;
      if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
        g.setEdge(edge.source, edge.target);
      }
    }

    dagre.layout(g);

    let maxBottom = yOffset;

    for (const nodeId of component) {
      if (!g.hasNode(nodeId)) continue;
      const { x, y, width, height } = g.node(nodeId);
      const position = { x: x - width / 2, y: y - height / 2 + yOffset };
      positions.set(nodeId, position);
      maxBottom = Math.max(maxBottom, position.y + height);
    }

    yOffset = maxBottom + componentGap;
  }

  return nodes.map((node) => (
    node.hidden || !positions.has(node.id)
      ? node
      : { ...node, position: positions.get(node.id)! }
  ));
}

// Collect all descendants of a set of node IDs
function descendants(
  rootIds: string[],
  childrenOf: Map<string, string[]>
): Set<string> {
  const hidden = new Set<string>();
  const queue = [...rootIds];
  while (queue.length) {
    const curr = queue.shift()!;
    for (const child of childrenOf.get(curr) ?? []) {
      if (!hidden.has(child)) {
        hidden.add(child);
        queue.push(child);
      }
    }
  }
  return hidden;
}

// --- Node type registry ---
const nodeTypes: NodeTypes = {
  entityNode:   EntityNode,
  categoryNode: CategoryNode,
  topicNode:    TopicNode,
  factNode:     FactNode,
  sourceNode:   SourceNode,
  specNode:     SpecNode,
};

// --- Main component ---
interface CanvasGraphProps {
  canvas: CanvasState | null | undefined;
}

export function CanvasGraph({ canvas }: CanvasGraphProps) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [pdfModal, setPdfModal] = useState<PDFModalState | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const handleOpenPDF = useCallback(
    (filename: string, page: number, highlights: PDFHighlight[]) =>
      setPdfModal({ filename, page, highlights }),
    []
  );

  const handleToggleCollapse = useCallback((id: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const rawNodes = canvas?.nodes ?? [];
  const relations = canvas?.relations ?? [];

  // Structural key — re-layout only when nodes/edges are added or removed,
  // not when content/status changes (so in-progress updates don't jump)
  const structureKey = useMemo(
    () =>
      rawNodes.map((n) => n.id).join(",") +
      "|" +
      relations.map((r) => `${r.from_id}>${r.to_id}`).join(",") +
      "|" +
      [...collapsedIds].sort().join(","),
    [rawNodes, relations, collapsedIds]
  );

  useEffect(() => {
    if (rawNodes.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const nodeMap = new Map(rawNodes.map((n) => [n.id, n]));

    // Build children map
    const childrenOf = new Map<string, string[]>();
    for (const r of relations) {
      const arr = childrenOf.get(r.from_id) ?? [];
      arr.push(r.to_id);
      childrenOf.set(r.from_id, arr);
    }

    const hiddenIds = descendants([...collapsedIds], childrenOf);

    // Pre-compute source children per fact node. Spec nodes are rendered
    // directly in the graph, not treated as source thumbnails.
    const factSources = new Map<string, CanvasNodeData[]>();
    for (const r of relations) {
      const from = nodeMap.get(r.from_id);
      const to = nodeMap.get(r.to_id);
      if (from?.node_type === "fact" && to?.node_type === "source") {
        const arr = factSources.get(r.from_id) ?? [];
        arr.push(to);
        factSources.set(r.from_id, arr);
      }
    }

    // Build RF nodes (no position yet — dagre will assign them)
    const rfNodes: Node[] = rawNodes.map((n) => {
      const hidden = hiddenIds.has(n.id);

      if (n.node_type === "entity") {
        return {
          id: n.id,
          type: "entityNode",
          position: { x: 0, y: 0 },
          hidden,
          data: {
            node: n,
            childCount: descendants([n.id], childrenOf).size,
            collapsed: collapsedIds.has(n.id),
            onToggleCollapse: handleToggleCollapse,
          },
        };
      }
      if (n.node_type === "category") {
        return {
          id: n.id,
          type: "categoryNode",
          position: { x: 0, y: 0 },
          hidden,
          data: {
            node: n,
            childCount: descendants([n.id], childrenOf).size,
            collapsed: collapsedIds.has(n.id),
            onToggleCollapse: handleToggleCollapse,
          },
        };
      }
      if (n.node_type === "topic") {
        return {
          id: n.id,
          type: "topicNode",
          position: { x: 0, y: 0 },
          hidden,
          data: {
            node: n,
            childCount: descendants([n.id], childrenOf).size,
            collapsed: collapsedIds.has(n.id),
            onToggleCollapse: handleToggleCollapse,
          },
        };
      }
      if (n.node_type === "fact") {
        return {
          id: n.id,
          type: "factNode",
          position: { x: 0, y: 0 },
          hidden,
          data: {
            node: n,
            sources: factSources.get(n.id) ?? [],
            onOpenPDF: handleOpenPDF,
          },
        };
      }
      if (n.node_type === "spec") {
        return {
          id: n.id,
          type: "specNode",
          position: { x: 0, y: 0 },
          hidden,
          data: { node: n },
        };
      }
      return {
        id: n.id,
        type: "sourceNode",
        position: { x: 0, y: 0 },
        hidden,
        data: { node: n, onOpenPDF: handleOpenPDF },
      };
    });

    const rfEdges: Edge[] = relations.map((r, idx) => {
      const fromNode = nodeMap.get(r.from_id);
      const toNode = nodeMap.get(r.to_id);
      const isEntityCat = fromNode?.node_type === "entity";
      const isCatTopic  = fromNode?.node_type === "category";
      const isTopicFact = (fromNode?.node_type === "topic" || fromNode?.node_type === "category") && toNode?.node_type === "fact";
      const isFactSrc   = fromNode?.node_type === "fact"  && toNode?.node_type === "source";
      const isSpec      = toNode?.node_type === "spec";
      const strokeColor = isEntityCat ? "#64748b"
        : isCatTopic  ? "#3b82f6"
        : isTopicFact ? "#f59e0b"
        : isSpec       ? "#8b5cf6"
        : isFactSrc    ? "#6366f1"
        : "#14b8a6";
      return {
        id: `e-${idx}`,
        source: r.from_id,
        target: r.to_id,
        label: r.label || undefined,
        type: "smoothstep",
        hidden: hiddenIds.has(r.from_id) || hiddenIds.has(r.to_id),
        animated: isEntityCat || isCatTopic,
        style: {
          stroke: strokeColor,
          strokeWidth: isEntityCat ? 2.5 : isCatTopic ? 2 : 1.5,
          strokeDasharray: isFactSrc || isSpec ? "4 3" : undefined,
        },
        labelStyle: { fill: "#6366f1", fontWeight: 500, fontSize: 10 },
        labelBgStyle: { fill: "#f5f3ff", fillOpacity: 0.9 },
        labelBgPadding: [3, 2] as [number, number],
      };
    });

    const laidOut = applyDagreLayout(rfNodes, rfEdges);
    setNodes(laidOut);
    setEdges(rfEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structureKey]);

  // Update node data (status, content) without re-layouting
  useEffect(() => {
    if (rawNodes.length === 0) return;
    const nodeMap = new Map(rawNodes.map((n) => [n.id, n]));
    const childrenOf = new Map<string, string[]>();
    for (const r of relations) {
      const arr = childrenOf.get(r.from_id) ?? [];
      arr.push(r.to_id);
      childrenOf.set(r.from_id, arr);
    }
    const factSources = new Map<string, CanvasNodeData[]>();
    for (const r of relations) {
      const from = nodeMap.get(r.from_id);
      const to = nodeMap.get(r.to_id);
      if (from?.node_type === "fact" && to?.node_type === "source") {
        const arr = factSources.get(r.from_id) ?? [];
        arr.push(to);
        factSources.set(r.from_id, arr);
      }
    }

    setNodes((prev) =>
      prev.map((rfNode) => {
        const n = nodeMap.get(rfNode.id);
        if (!n) return rfNode;
        if (n.node_type === "entity" || n.node_type === "category" || n.node_type === "topic") {
          return { ...rfNode, data: { ...rfNode.data, node: n, childCount: descendants([n.id], childrenOf).size, collapsed: collapsedIds.has(n.id), onToggleCollapse: handleToggleCollapse } };
        }
        if (n.node_type === "fact") {
          return { ...rfNode, data: { ...rfNode.data, node: n, sources: factSources.get(n.id) ?? [], onOpenPDF: handleOpenPDF } };
        }
        if (n.node_type === "spec") {
          return { ...rfNode, data: { ...rfNode.data, node: n } };
        }
        return { ...rfNode, data: { ...rfNode.data, node: n } };
      })
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawNodes, relations]);

  if (rawNodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="h-16 w-16 rounded-2xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center mb-4">
          <Network size={28} className="text-neutral-400 dark:text-neutral-500" />
        </div>
        <h3 className="text-base font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
          Canvas is empty
        </h3>
        <p className="text-sm text-neutral-400 dark:text-neutral-500 max-w-xs">
          Ask a technical question — the agent will build a knowledge graph with
          topics, facts, and source references.
        </p>
      </div>
    );
  }

  return (
    <>
      <div
        className="w-full rounded-xl border border-neutral-200 dark:border-neutral-800 overflow-hidden"
        style={{ height: "calc(100vh - 260px)", minHeight: 400 }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.1}
          maxZoom={2.5}
          proOptions={{ hideAttribution: true }}
          nodesDraggable
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1.2}
            className="!bg-neutral-50 dark:!bg-neutral-950"
          />
          <Controls className="!bg-white dark:!bg-neutral-900 !border-neutral-200 dark:!border-neutral-800 !shadow-sm" />
          <MiniMap
            className="!bg-white dark:!bg-neutral-900 !border-neutral-200 dark:!border-neutral-800"
            nodeStrokeColor="#6366f1"
            nodeColor="#e0e7ff"
            maskColor="rgba(0,0,0,0.06)"
          />
        </ReactFlow>
      </div>

      {pdfModal && (
        <PDFModal
          filename={pdfModal.filename}
          initialPage={pdfModal.page}
          highlights={pdfModal.highlights}
          onClose={() => setPdfModal(null)}
        />
      )}
    </>
  );
}
