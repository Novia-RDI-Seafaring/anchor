"use client";

import React, { useState, useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Network } from "lucide-react";
import {
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

// --- Layout ---
const TOPIC_W = 220;
const FACT_W  = 220;
const SRC_W   = 160;
const SPEC_W  = 220;
const H_GAP   = 24;
const TOPIC_Y = 0;
const FACT_Y  = 180;
const SRC_Y   = 360;

function computeLayout(
  nodes: CanvasNodeData[],
  relations: Relation[]
): Record<string, { x: number; y: number }> {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Build children map (from_id → [to_id])
  const childrenOf = new Map<string, string[]>();
  for (const r of relations) {
    const arr = childrenOf.get(r.from_id) ?? [];
    arr.push(r.to_id);
    childrenOf.set(r.from_id, arr);
  }

  const positioned = new Set<string>();
  const pos: Record<string, { x: number; y: number }> = {};
  let cursorX = 0;

  const topics = nodes.filter((n) => n.node_type === "topic");

  for (const topic of topics) {
    const factIds = (childrenOf.get(topic.id) ?? []).filter(
      (id) => nodeMap.get(id)?.node_type === "fact" || nodeMap.get(id)?.node_type === "spec"
    );

    if (factIds.length === 0) {
      pos[topic.id] = { x: cursorX, y: TOPIC_Y };
      positioned.add(topic.id);
      cursorX += TOPIC_W + H_GAP;
      continue;
    }

    const topicStartX = cursorX;
    let factCursorX = cursorX;

    for (const factId of factIds) {
      const srcIds = (childrenOf.get(factId) ?? []).filter(
        (id) => ["source", "spec"].includes(nodeMap.get(id)?.node_type ?? "")
      );
      const neededW = Math.max(FACT_W, srcIds.length * (SRC_W + H_GAP) - H_GAP);

      pos[factId] = { x: factCursorX, y: FACT_Y };
      positioned.add(factId);

      let srcX = factCursorX;
      for (const srcId of srcIds) {
        pos[srcId] = { x: srcX, y: SRC_Y };
        positioned.add(srcId);
        srcX += SRC_W + H_GAP;
      }

      factCursorX += neededW + H_GAP;
    }

    const groupWidth = factCursorX - topicStartX - H_GAP;
    pos[topic.id] = {
      x: topicStartX + groupWidth / 2 - TOPIC_W / 2,
      y: TOPIC_Y,
    };
    positioned.add(topic.id);
    cursorX = factCursorX + 20;
  }

  // Orphan facts / sources / specs
  for (const n of nodes) {
    if (!positioned.has(n.id)) {
      const y = n.node_type === "fact" ? FACT_Y
              : n.node_type === "source" || n.node_type === "spec" ? SRC_Y
              : TOPIC_Y;
      pos[n.id] = { x: cursorX, y };
      cursorX += (n.node_type === "source" ? SRC_W : n.node_type === "spec" ? SPEC_W : FACT_W) + H_GAP;
    }
  }

  return pos;
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
  topicNode: TopicNode,
  factNode: FactNode,
  sourceNode: SourceNode,
  specNode: SpecNode,
};

// --- Main component ---
interface CanvasGraphProps {
  canvas: CanvasState | null | undefined;
}

export function CanvasGraph({ canvas }: CanvasGraphProps) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [pdfModal, setPdfModal] = useState<PDFModalState | null>(null);

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

  const { nodes, edges } = useMemo(() => {
    if (rawNodes.length === 0) return { nodes: [], edges: [] };

    const nodeMap = new Map(rawNodes.map((n) => [n.id, n]));

    // Build children map
    const childrenOf = new Map<string, string[]>();
    for (const r of relations) {
      const arr = childrenOf.get(r.from_id) ?? [];
      arr.push(r.to_id);
      childrenOf.set(r.from_id, arr);
    }

    // Compute hidden nodes from collapsed topics
    const hiddenIds = descendants([...collapsedIds], childrenOf);

    // For each fact, pre-compute its connected source nodes (source + spec treated as leaf evidence)
    const factSources = new Map<string, CanvasNodeData[]>();
    for (const r of relations) {
      const from = nodeMap.get(r.from_id);
      const to = nodeMap.get(r.to_id);
      if (from?.node_type === "fact" && (to?.node_type === "source" || to?.node_type === "spec")) {
        const arr = factSources.get(r.from_id) ?? [];
        arr.push(to);
        factSources.set(r.from_id, arr);
      }
    }

    const layout = computeLayout(rawNodes, relations);

    // Count direct fact children per topic (for collapse badge)
    const topicFactCount = new Map<string, number>();
    for (const r of relations) {
      if (nodeMap.get(r.from_id)?.node_type === "topic" && nodeMap.get(r.to_id)?.node_type === "fact") {
        topicFactCount.set(r.from_id, (topicFactCount.get(r.from_id) ?? 0) + 1);
      }
    }

    const rfNodes: Node[] = rawNodes.map((n) => {
      const base = {
        id: n.id,
        position: layout[n.id] ?? { x: 0, y: 0 },
        hidden: hiddenIds.has(n.id),
      };

      if (n.node_type === "topic") {
        return {
          ...base,
          type: "topicNode",
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
          ...base,
          type: "factNode",
          data: {
            node: n,
            sources: factSources.get(n.id) ?? [],
            onOpenPDF: handleOpenPDF,
          },
        };
      }
      if (n.node_type === "spec") {
        return {
          ...base,
          type: "specNode",
          data: { node: n },
        };
      }
      // source — highlights come directly from node.highlights
      return {
        ...base,
        type: "sourceNode",
        data: {
          node: n,
          onOpenPDF: handleOpenPDF,
        },
      };
    });

    const rfEdges: Edge[] = relations.map((r, idx) => {
      const fromNode = nodeMap.get(r.from_id);
      const toNode = nodeMap.get(r.to_id);

      // Edge style by relationship type
      const isTopicFact = fromNode?.node_type === "topic" && toNode?.node_type === "fact";
      const isFactSrc   = fromNode?.node_type === "fact"  && toNode?.node_type === "source";
      const isSpec      = toNode?.node_type === "spec";

      return {
        id: `e-${idx}`,
        source: r.from_id,
        target: r.to_id,
        label: r.label || undefined,
        type: "smoothstep",
        hidden: hiddenIds.has(r.from_id) || hiddenIds.has(r.to_id),
        animated: isTopicFact,
        style: {
          stroke: isTopicFact ? "#f59e0b" : isSpec ? "#8b5cf6" : isFactSrc ? "#6366f1" : "#14b8a6",
          strokeWidth: isTopicFact ? 2 : 1.5,
          strokeDasharray: isFactSrc || isSpec ? "4 3" : undefined,
        },
        labelStyle: { fill: "#6366f1", fontWeight: 500, fontSize: 10 },
        labelBgStyle: { fill: "#f5f3ff", fillOpacity: 0.9 },
        labelBgPadding: [3, 2] as [number, number],
      };
    });

    return { nodes: rfNodes, edges: rfEdges };
  }, [rawNodes, relations, collapsedIds, handleToggleCollapse, handleOpenPDF]);

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
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.15}
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
