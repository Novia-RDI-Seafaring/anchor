"use client";

import React, { useState, useMemo, useCallback, useEffect, useRef } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  SelectionMode,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  BackgroundVariant,
} from "@xyflow/react";
import { FloatingEdge } from "./FloatingEdge";
import { AnchoredEdge } from "./AnchoredEdge";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import { Network, UploadCloud, Layers, Box, MessageSquare, Palette, MousePointer2, Hand, Filter, SquareDashed, Wand2, Square, Circle, Diamond, ArrowRight, BookOpen, Type, Trash2 } from "lucide-react";
import {
  ConceptNode,
  EntityNode,
  CategoryNode,
  TopicNode,
  FactNode,
  SourceNode,
  SpecNode,
  DocumentNode,
  ImageNode,
  FmuNode,
  PlotNode,
  FunnelNode,
  AreaNode,
  type CanvasNodeData,
  type ConceptNodeData,
  type DocumentNodeData,
  type FmuNodeData,
  type PlotNodeData,
  type FunnelNodeData,
  type AreaNodeData,
} from "./KnowledgeNodes";
import {
  adaptDocumentToCanvasItem,
  adaptLegacyNodeToCanvasItem,
  type CanvasItem,
  type LegacyCanvasNode,
} from "./canvas-model";
import { PDFModal, type PDFHighlight } from "./PDFModal";
import { useApp, type KBDocument } from "@/contexts/AppContext";
import { API_URL } from "@/lib/api-config";

// --- Types ---
interface Relation {
  from_id: string;
  to_id: string;
  label: string;
  source_handle?: string;
  target_handle?: string;
  document_id?: string;
  page?: number;
  bbox?: number[];
  highlights?: PDFHighlight[];
}

interface CanvasState {
  nodes: LegacyCanvasNode[];
  relations: Relation[];
}

interface FlowPosition {
  x: number;
  y: number;
}

interface PDFModalState {
  filename: string;
  page: number;
  highlights: PDFHighlight[];
}

type CollapsibleNodeType = "concept" | "entity" | "category" | "topic";

// --- Node sizes (width × height in px) used by dagre for spacing ---
const NODE_SIZE: Record<string, { w: number; h: number }> = {
  conceptNode:  { w: 240, h: 60  },
  entityNode:   { w: 280, h: 70  },
  categoryNode: { w: 220, h: 55  },
  topicNode:    { w: 240, h: 60  },
  factNode:     { w: 280, h: 100 },
  documentNode: { w: 150, h: 64  },
  sourceNode:   { w: 180, h: 40  },
  specNode:     { w: 420, h: 200 },
  fmuNode:      { w: 280, h: 200 },
  plotNode:     { w: 320, h: 220 },
  imageNode:    { w: 300, h: 200 },
  funnelNode:   { w: 120, h: 90  },
  areaNode:     { w: 600, h: 400 },
};
const DEFAULT_SIZE = { w: 220, h: 80 };
const DOCUMENT_NODE_SIZE = { w: 150, h: 64 };
const KNOWLEDGE_FILE_PATTERN = /\.(pdf|docx|txt|md|html)$/i;

function anchorAtCenter(position: FlowPosition, size: { w: number; h: number }): FlowPosition {
  return {
    x: position.x - size.w / 2,
    y: position.y - size.h / 2,
  };
}

function inferNodeSize(node: Node): { w: number; h: number } {
  const width = typeof node.width === "number"
    ? node.width
    : typeof node.measured?.width === "number"
    ? node.measured.width
    : typeof node.style?.width === "number"
    ? node.style.width
    : NODE_SIZE[node.type ?? ""]?.w ?? DEFAULT_SIZE.w;
  const height = typeof node.height === "number"
    ? node.height
    : typeof node.measured?.height === "number"
    ? node.measured.height
    : typeof node.style?.height === "number"
    ? node.style.height
    : NODE_SIZE[node.type ?? ""]?.h ?? DEFAULT_SIZE.h;
  return { w: width, h: height };
}

function findBestAreaParent(
  absolutePosition: FlowPosition,
  nodeSize: { w: number; h: number },
  nodes: Node[],
  excludeNodeId?: string,
): { id: string; position: FlowPosition } | null {
  let bestParent: { id: string; ratio: number; position: FlowPosition } | null = null;

  for (const candidate of nodes) {
    if (candidate.type !== "areaNode" || candidate.id === excludeNodeId) continue;
    const areaSize = inferNodeSize(candidate);
    const overlapWidth = Math.max(
      0,
      Math.min(absolutePosition.x + nodeSize.w, candidate.position.x + areaSize.w) - Math.max(absolutePosition.x, candidate.position.x)
    );
    const overlapHeight = Math.max(
      0,
      Math.min(absolutePosition.y + nodeSize.h, candidate.position.y + areaSize.h) - Math.max(absolutePosition.y, candidate.position.y)
    );
    const overlapRatio = (overlapWidth * overlapHeight) / Math.max(1, nodeSize.w * nodeSize.h);
    if (overlapRatio > 0.5 && (!bestParent || overlapRatio > bestParent.ratio)) {
      bestParent = {
        id: candidate.id,
        ratio: overlapRatio,
        position: {
          x: absolutePosition.x - candidate.position.x,
          y: absolutePosition.y - candidate.position.y,
        },
      };
    }
  }

  return bestParent ? { id: bestParent.id, position: bestParent.position } : null;
}

// --- Source provenance utilities ---
const SOURCE_COLORS = [
  '#ef4444', '#f59e0b', '#10b981', '#3b82f6',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316',
];

function buildSourceColorMap(workspaceDocIds: string[]): Map<string, string> {
  const map = new Map<string, string>();
  workspaceDocIds.forEach((docId, i) => {
    map.set(`__doc_${docId}`, SOURCE_COLORS[i % SOURCE_COLORS.length]!);
  });
  return map;
}

interface ProvenanceInput {
  id: string;
  parent_id?: string;
}

function computeNodeSources(
  nodes: ProvenanceInput[],
  relations: { from_id: string; to_id: string }[],
): Map<string, Set<string>> {
  // Build reverse adjacency: who points TO each node?
  const inbound = new Map<string, string[]>();
  for (const r of relations) {
    const arr = inbound.get(r.to_id) ?? [];
    arr.push(r.from_id);
    inbound.set(r.to_id, arr);
  }
  const parentOf = new Map<string, string>();
  for (const n of nodes) {
    if (n.parent_id) parentOf.set(n.id, n.parent_id);
  }
  const cache = new Map<string, Set<string>>();

  function walk(nodeId: string, visited: Set<string>): Set<string> {
    if (cache.has(nodeId)) return cache.get(nodeId)!;
    if (visited.has(nodeId)) return new Set();
    visited.add(nodeId);

    const sources = new Set<string>();
    if (nodeId.startsWith('__doc_')) {
      sources.add(nodeId);
      cache.set(nodeId, sources);
      return sources;
    }
    for (const pred of (inbound.get(nodeId) ?? [])) {
      for (const s of walk(pred, visited)) sources.add(s);
    }
    const parent = parentOf.get(nodeId);
    if (parent) {
      for (const s of walk(parent, visited)) sources.add(s);
    }
    cache.set(nodeId, sources);
    return sources;
  }

  const result = new Map<string, Set<string>>();
  for (const n of nodes) {
    result.set(n.id, walk(n.id, new Set()));
  }
  // Also compute for __doc_ nodes not in the nodes list but referenced in relations
  for (const r of relations) {
    for (const nid of [r.from_id, r.to_id]) {
      if (!result.has(nid) && nid.startsWith('__doc_')) {
        result.set(nid, new Set([nid]));
      }
    }
  }
  return result;
}

function pickEdgeSourceColor(
  sourceNodeSources: Set<string> | undefined,
  colorMap: Map<string, string>,
): string | null {
  if (!sourceNodeSources || sourceNodeSources.size === 0) return null;
  // Use first matched color
  for (const docNodeId of sourceNodeSources) {
    const c = colorMap.get(docNodeId);
    if (c) return c;
  }
  return null;
}

function buildDerivedEvidenceRelations(
  nodes: CanvasItem[],
  relations: Relation[],
  documents: KBDocument[],
): Relation[] {
  const existing = new Set(
    relations.map((r) => `${r.from_id}>${r.to_id}>${r.source_handle ?? ""}>${r.target_handle ?? ""}`),
  );
  const filenameToDocNode = new Map(documents.map((doc) => [doc.filename, `__doc_${doc.document_id}`]));
  const filenameToDocId = new Map(documents.map((doc) => [doc.filename, doc.document_id]));
  const derived: Relation[] = [];
  const seen = new Set<string>();

  const addEvidence = (
    fromId: string,
    source: {
      doc_id?: string;
      filename?: string;
      page?: number;
      bbox?: number[];
      highlights?: PDFHighlight[];
    },
    targetHandle?: string,
  ) => {
    const docNodeId = source.doc_id
      ? `__doc_${source.doc_id}`
      : (source.filename ? filenameToDocNode.get(source.filename) : undefined);
    if (!docNodeId || docNodeId === fromId) return;

    const key = `${fromId}>${docNodeId}>doc-evidence-out>${targetHandle ?? ""}`;
    if (existing.has(key) || seen.has(key)) return;
    seen.add(key);

    const page = typeof source.page === "number" ? source.page : 0;
    const bbox = Array.isArray(source.bbox) ? source.bbox : [];
    const highlights = source.highlights ?? (page > 0 && bbox.length === 4 ? [{ page, bbox }] : []);

    derived.push({
      from_id: fromId,
      to_id: docNodeId,
      label: page > 0 ? `p.${page}` : "",
      source_handle: targetHandle,
      target_handle: "doc-evidence-out",
      document_id: source.doc_id || (source.filename ? filenameToDocId.get(source.filename) : undefined),
      page,
      bbox,
      highlights,
    });
  };

  for (const node of nodes) {
    if (node.id.startsWith("__doc_")) continue;

    if (Array.isArray(node.parameter_sections)) {
      node.parameter_sections.forEach((section, sectionIndex) => {
        (section.rows ?? []).forEach((row, rowIndex) => {
          if (row?.source) addEvidence(node.id, row.source, `spec-row-in-${sectionIndex}-${rowIndex}`);
        });
      });
    }

    if (Array.isArray(node.properties)) {
      node.properties.forEach((prop, propertyIndex) => {
        addEvidence(node.id, {
          filename: prop?.ref_filename,
          page: prop?.ref_page,
          bbox: prop?.ref_bbox,
          highlights: prop?.ref_highlights as PDFHighlight[] | undefined,
        }, `spec-prop-in-${propertyIndex}`);
      });
    }

    if (node.filename && node.page && !node.id.startsWith("__doc_")) {
      addEvidence(node.id, {
        filename: node.filename,
        page: node.page,
        bbox: node.bbox,
        highlights: node.highlights as PDFHighlight[] | undefined,
      });
    }
  }

  return derived;
}

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

function applyMindmapLayout(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes;

  // Build parent→children (ignoring doc nodes)
  const childrenOf = new Map<string, string[]>();
  const hasParent = new Set<string>();
  for (const edge of edges) {
    if (edge.hidden || edge.target.startsWith('__doc_')) continue;
    const ch = childrenOf.get(edge.source) ?? [];
    ch.push(edge.target);
    childrenOf.set(edge.source, ch);
    hasParent.add(edge.target);
  }

  const visibleIds = new Set(nodes.filter(n => !n.hidden).map(n => n.id));
  const roots = nodes.filter(n =>
    !n.hidden && !n.id.startsWith('__doc_') && !hasParent.has(n.id)
  );

  const positions = new Map<string, { x: number; y: number }>();

  const TOPIC_R = 380;      // radius: concept → topic
  const LEAF_R  = 310;      // extra radius: topic → leaf
  const CLUSTER_W = 1150;   // horizontal gap between concept clusters

  roots.forEach((root, rootIdx) => {
    const cx = rootIdx * CLUSTER_W;
    positions.set(root.id, { x: cx, y: 0 });

    const topics = (childrenOf.get(root.id) ?? []).filter(id => visibleIds.has(id));
    const N = topics.length;

    topics.forEach((topicId, i) => {
      // Distribute topics evenly around the concept, starting from top
      const angle = N <= 1 ? -Math.PI / 2 : -Math.PI / 2 + (2 * Math.PI * i) / N;
      const tx = cx + TOPIC_R * Math.cos(angle);
      const ty = TOPIC_R * Math.sin(angle);
      positions.set(topicId, { x: tx, y: ty });

      const leaves = (childrenOf.get(topicId) ?? []).filter(id => visibleIds.has(id));
      const M = leaves.length;
      leaves.forEach((leafId, j) => {
        // Fan leaves in a 70° arc extending outward from concept→topic direction
        const spread = Math.PI / (M <= 1 ? 1 : 2.2);
        const leafAngle = M <= 1 ? angle : angle - spread / 2 + (spread * j) / (M - 1);
        positions.set(leafId, {
          x: tx + LEAF_R * Math.cos(leafAngle),
          y: ty + LEAF_R * Math.sin(leafAngle),
        });
      });
    });
  });

  // Doc nodes: row above all clusters
  const docNodes = nodes.filter(n => !n.hidden && n.id.startsWith('__doc_'));
  const docSpacing = 230;
  const totalDocW = (docNodes.length - 1) * docSpacing;
  const docCenterX = roots.length > 0
    ? roots.reduce((s, _, i) => s + i * CLUSTER_W, 0) / roots.length
    : 0;
  docNodes.forEach((dn, i) => {
    positions.set(dn.id, { x: docCenterX - totalDocW / 2 + i * docSpacing, y: -360 });
  });

  // Fallback: any visible node not yet positioned → stack below clusters
  let fallbackX = 0;
  for (const node of nodes) {
    if (node.hidden || positions.has(node.id)) continue;
    positions.set(node.id, { x: fallbackX, y: 800 });
    fallbackX += 280;
  }

  return nodes.map(node =>
    node.hidden || !positions.has(node.id)
      ? node
      : { ...node, position: positions.get(node.id)! }
  );
}

function placeNodesManually(
  nodes: Node[],
  relationParentOf: Map<string, string>,
  overrides: Record<string, FlowPosition>,
  existingPositions: Map<string, FlowPosition>,
): Node[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const relationChildren = new Map<string, string[]>();
  for (const [childId, parentId] of relationParentOf.entries()) {
    const arr = relationChildren.get(parentId) ?? [];
    arr.push(childId);
    relationChildren.set(parentId, arr);
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
      const pos = {
        x: 40 + (siblingIndex % 2) * 220,
        y: 56 + Math.floor(siblingIndex / 2) * 120,
      };
      positioned.set(nodeId, pos);
      return pos;
    }

    const relationParentId = relationParentOf.get(nodeId);
    if (relationParentId && !lineage.has(nodeId)) {
      const nextLineage = new Set(lineage);
      nextLineage.add(nodeId);
      const parentPos = resolve(relationParentId, nextLineage);
      const siblings = relationChildren.get(relationParentId) ?? [];
      const siblingIndex = Math.max(0, siblings.indexOf(nodeId));
      const spread = siblings.length <= 1 ? 0 : (siblingIndex - (siblings.length - 1) / 2) * 120;
      const pos = {
        x: parentPos.x + 280,
        y: parentPos.y + spread,
      };
      positioned.set(nodeId, pos);
      return pos;
    }

    const pos = {
      x: (nodeIndex % 4) * 320,
      y: 120 + Math.floor(nodeIndex / 4) * 180,
    };
    positioned.set(nodeId, pos);
    return pos;
  };

  return nodes.map((node) => ({
    ...node,
    position: resolve(node.id),
  }));
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

// --- Color accent for nodes ---
const COLOR_HEX: Record<string, string> = {
  violet:  '#8b5cf6',
  blue:    '#3b82f6',
  emerald: '#10b981',
  amber:   '#f59e0b',
  rose:    '#f43f5e',
  indigo:  '#6366f1',
  slate:   '#64748b',
};

function nodeStyle(color?: string): React.CSSProperties | undefined {
  if (!color || !COLOR_HEX[color]) return undefined;
  return { boxShadow: `0 0 0 2.5px ${COLOR_HEX[color]}, 0 2px 8px rgba(0,0,0,0.08)`, borderRadius: 12 };
}

const COLLAPSIBLE_NODE_COMPONENTS: Record<CollapsibleNodeType, string> = {
  concept: "conceptNode",
  entity: "entityNode",
  category: "categoryNode",
  topic: "topicNode",
};

function isCollapsibleNodeType(nodeType: CanvasItem["semanticType"]): nodeType is CollapsibleNodeType {
  return nodeType === "concept" || nodeType === "entity" || nodeType === "category" || nodeType === "topic";
}

function buildFlowNode(
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

function applyExplicitNodeSize(node: CanvasItem, rfNode: Node, fallback: { w: number; h: number }): Node {
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

function buildCollapsibleNodeData(
  node: CanvasItem,
  childrenOf: Map<string, string[]>,
  collapsedIds: Set<string>,
  onToggleCollapse: (id: string) => void,
  onDelete?: (id: string) => void,
) {
  return {
    node,
    childCount: descendants([node.id], childrenOf).size,
    collapsed: collapsedIds.has(node.id),
    onToggleCollapse,
    onDelete,
  };
}

function getEvidenceData(
  nodeId: string,
  relations: Relation[],
  documents: KBDocument[],
) {
  const relation = relations.find((item) => item.from_id === nodeId && item.to_id.startsWith("__doc_"));
  const document = relation ? documents.find((item) => item.document_id === relation.document_id) : undefined;
  return {
    evidenceFilename: document?.filename,
    evidencePage: relation?.page,
    evidenceHighlights: relation?.highlights,
  };
}

function setCustomDragPreview(
  event: React.DragEvent<HTMLElement>,
  options: {
    label: string;
    width: number;
    height: number;
    className: string;
  },
) {
  const preview = document.createElement("div");
  preview.className = `fixed -left-[9999px] -top-[9999px] pointer-events-none flex items-center justify-center rounded-xl border-2 shadow-xl text-sm font-semibold ${options.className}`;
  preview.style.width = `${options.width}px`;
  preview.style.height = `${options.height}px`;
  preview.style.padding = "0 14px";
  preview.textContent = options.label;
  document.body.appendChild(preview);
  event.dataTransfer.setDragImage(preview, options.width / 2, options.height / 2);
  requestAnimationFrame(() => preview.remove());
}

type NewNodeType = 'concept' | 'entity' | 'fact' | 'funnel' | 'area';
type CanvasTool = "move" | "select" | "connect" | NewNodeType;

function isInsertTool(tool: CanvasTool): tool is NewNodeType {
  return tool === "concept" || tool === "entity" || tool === "fact" || tool === "funnel" || tool === "area";
}

function LeftToolRail({
  activeTool,
  onChange,
  onArrange,
  onToggleLibrary,
  libraryOpen,
}: {
  activeTool: CanvasTool;
  onChange: (t: CanvasTool) => void;
  onArrange?: () => void;
  onToggleLibrary?: () => void;
  libraryOpen?: boolean;
}) {
  const primaryTools: Array<{ id: CanvasTool; icon: React.ReactNode; label: string; shortcut?: string }> = [
    { id: "select", icon: <Hand size={15} />, label: "Board", shortcut: "V" },
    { id: "connect", icon: <ArrowRight size={15} />, label: "Arrow", shortcut: "A" },
  ];
  const insertTools: Array<{ id: CanvasTool; icon: React.ReactNode; label: string; shortcut?: string }> = [
    { id: "concept", icon: <Square size={15} />, label: "Box", shortcut: "1" },
    { id: "entity", icon: <Circle size={15} />, label: "Circle", shortcut: "2" },
    { id: "funnel", icon: <Diamond size={15} />, label: "Diamond", shortcut: "3" },
    { id: "area", icon: <SquareDashed size={15} />, label: "Area", shortcut: "4" },
    { id: "fact", icon: <Type size={15} />, label: "Text", shortcut: "5" },
  ];

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
      if (e.key === "v" || e.key === "V") onChange("select");
      if (e.key === "1") onChange("concept");
      if (e.key === "2") onChange("entity");
      if (e.key === "3") onChange("funnel");
      if (e.key === "4") onChange("area");
      if (e.key === "5") onChange("fact");
      if (e.key === "a" || e.key === "A") onChange("connect");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onChange]);

  return (
    <div className="absolute left-4 top-20 z-30 flex flex-col gap-2 rounded-[22px] border border-neutral-200/80 bg-white/94 p-2 shadow-[0_14px_40px_rgba(15,23,42,0.10)] backdrop-blur-md dark:border-neutral-700/80 dark:bg-neutral-900/94">
      <div className="flex flex-col gap-1.5">
        {primaryTools.map((tool) => (
          <button
            key={tool.id}
            onClick={() => onChange(tool.id)}
            title={tool.shortcut ? `${tool.label} (${tool.shortcut})` : tool.label}
            className={`flex h-10 w-10 items-center justify-center rounded-2xl border transition-colors ${
              activeTool === tool.id
                ? "border-indigo-300 bg-indigo-100 text-indigo-700 dark:border-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-300"
                : "border-transparent text-neutral-500 hover:border-neutral-200 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:border-neutral-700 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
            }`}
          >
            {tool.icon}
          </button>
        ))}
      </div>
      <div className="mx-auto h-px w-8 bg-neutral-200 dark:bg-neutral-700" />
      <div className="flex flex-col gap-1.5">
        {insertTools.map((tool) => (
          <button
            key={tool.id}
            onClick={() => onChange(tool.id)}
            title={tool.shortcut ? `${tool.label} (${tool.shortcut})` : tool.label}
            className={`flex h-10 w-10 items-center justify-center rounded-2xl border transition-colors ${
              activeTool === tool.id
                ? "border-indigo-300 bg-indigo-100 text-indigo-700 dark:border-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-300"
                : "border-transparent text-neutral-500 hover:border-neutral-200 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:border-neutral-700 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
            }`}
          >
            {tool.icon}
          </button>
        ))}
      </div>
      <div className="mx-auto h-px w-8 bg-neutral-200 dark:bg-neutral-700" />
      <div className="flex flex-col gap-1.5">
        <button
          onClick={onArrange}
          title="Arrange canvas"
          className="flex h-10 w-10 items-center justify-center rounded-2xl border border-transparent text-neutral-500 transition-colors hover:border-neutral-200 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:border-neutral-700 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
        >
          <Wand2 size={15} />
        </button>
        {!libraryOpen && (
          <button
            onClick={onToggleLibrary}
            title="Toggle library"
            className="flex h-10 w-10 items-center justify-center rounded-2xl border border-transparent text-neutral-500 transition-colors hover:border-neutral-200 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:border-neutral-700 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
          >
            <BookOpen size={15} />
          </button>
        )}
      </div>
    </div>
  );
}

function SelectionInspector({
  node,
  onSetColor,
  onDelete,
}: {
  node: CanvasItem | null;
  onSetColor?: (nodeId: string, color: string) => void;
  onDelete?: (nodeId: string) => void;
}) {
  if (!node) return null;
  const heading = node.semanticType === "document" ? "Document" : node.semanticType.charAt(0).toUpperCase() + node.semanticType.slice(1);
  const previewText = node.text || node.title || node.funnel_label || node.area_label || node.spec_title || node.metadata?.document?.filename || "Untitled";
  return (
    <div className="absolute right-4 top-20 z-20 w-64 rounded-[24px] border border-neutral-200/80 bg-white/95 p-4 shadow-[0_16px_40px_rgba(15,23,42,0.10)] backdrop-blur-md dark:border-neutral-700/80 dark:bg-neutral-900/95">
      <div className="mb-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-400">Properties</p>
        <p className="mt-1 text-sm font-semibold text-neutral-900 dark:text-neutral-100">{heading}</p>
        <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">{previewText}</p>
      </div>
      <div className="mb-4">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-neutral-400">Accent</p>
        <div className="flex flex-wrap gap-1.5">
          {CTX_COLORS.map((c) => (
            <button
              key={c.name}
              title={c.label}
              onClick={() => onSetColor?.(node.id, c.name)}
              className={`h-6 w-6 rounded-full border-2 transition-transform hover:scale-110 ${node.color === c.name || (!node.color && !c.name) ? "border-neutral-900 dark:border-white" : "border-white dark:border-neutral-800"}`}
              style={{ background: c.hex }}
            />
          ))}
        </div>
      </div>
      <div className="flex items-center justify-between rounded-2xl bg-neutral-50 px-3 py-2 text-[11px] text-neutral-500 dark:bg-neutral-800/70 dark:text-neutral-400">
        <span>ID</span>
        <span className="max-w-[120px] truncate font-mono">{node.id}</span>
      </div>
      {onDelete && (
        <button
          onClick={() => onDelete(node.id)}
          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl border border-red-200 px-3 py-2 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-900/60 dark:text-red-400 dark:hover:bg-red-950/30"
        >
          <Trash2 size={13} />
          Remove
        </button>
      )}
    </div>
  );
}

// --- Node context menu (right-click) ---
const CTX_COLORS = [
  { name: '',        hex: '#94a3b8', label: 'Default' },
  { name: 'violet',  hex: '#8b5cf6', label: 'Violet' },
  { name: 'indigo',  hex: '#6366f1', label: 'Indigo' },
  { name: 'blue',    hex: '#3b82f6', label: 'Blue' },
  { name: 'emerald', hex: '#10b981', label: 'Green' },
  { name: 'amber',   hex: '#f59e0b', label: 'Amber' },
  { name: 'rose',    hex: '#f43f5e', label: 'Rose' },
  { name: 'slate',   hex: '#64748b', label: 'Slate' },
];

function NodeContextMenu({
  nodeId, top, left, right, bottom, onSetColor, onDelete, onClose,
}: {
  nodeId: string;
  top?: number | false; left?: number | false;
  right?: number | false; bottom?: number | false;
  onSetColor: (id: string, color: string) => void;
  onDelete?: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <div
      style={{ top: top || undefined, left: left || undefined, right: right || undefined, bottom: bottom || undefined }}
      className="absolute z-50 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-xl shadow-xl p-2.5 w-44"
    >
      <div className="flex items-center gap-1.5 mb-2">
        <Palette size={11} className="text-neutral-400" />
        <p className="text-[10px] text-neutral-400 font-semibold uppercase tracking-wide">Color</p>
      </div>
      <div className="flex gap-1.5 flex-wrap mb-2.5">
        {CTX_COLORS.map(c => (
          <button
            key={c.name}
            title={c.label}
            onClick={() => { onSetColor(nodeId, c.name); onClose(); }}
            className="w-5 h-5 rounded-full border-2 border-white dark:border-neutral-800 shadow-sm hover:scale-125 transition-transform"
            style={{ background: c.hex }}
          />
        ))}
      </div>
      {onDelete && (
        <>
          <hr className="border-neutral-200 dark:border-neutral-700 mb-1.5" />
          <button
            onClick={() => { onDelete(nodeId); onClose(); }}
            className="w-full text-left text-xs text-red-500 hover:text-red-600 dark:text-red-400 px-1 py-0.5 rounded hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
          >
            Delete node
          </button>
        </>
      )}
    </div>
  );
}

// --- Node type registry ---
const nodeTypes: NodeTypes = {
  conceptNode:  ConceptNode,
  entityNode:   EntityNode,
  categoryNode: CategoryNode,
  topicNode:    TopicNode,
  factNode:     FactNode,
  sourceNode:   SourceNode,
  specNode:     SpecNode,
  documentNode: DocumentNode,
  fmuNode:      FmuNode,
  plotNode:     PlotNode,
  imageNode:    ImageNode,
  funnelNode:   FunnelNode,
  areaNode:     AreaNode,
};

const edgeTypes: EdgeTypes = {
  floating: FloatingEdge,
  anchored: AnchoredEdge,
};

// --- New node picker popup ---

function NewNodePicker({
  screenX,
  screenY,
  onConfirm,
  onCancel,
}: {
  screenX: number;
  screenY: number;
  onConfirm: (type: NewNodeType, label: string) => void;
  onCancel: () => void;
}) {
  const [type, setType] = useState<NewNodeType>('concept');
  const [label, setLabel] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') { e.preventDefault(); if (label.trim()) onConfirm(type, label.trim()); }
    else if (e.key === 'Escape') { onCancel(); }
  };

  const types: { id: NewNodeType; label: string }[] = [
    { id: 'concept', label: 'Concept' },
    { id: 'entity',  label: 'Entity'  },
    { id: 'fact',    label: 'Fact'    },
    { id: 'funnel',  label: 'Funnel'  },
    { id: 'area',    label: 'Area'    },
  ];

  const clampedX = Math.min(screenX, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 248);
  const clampedY = Math.min(screenY, (typeof window !== 'undefined' ? window.innerHeight : 800) - 180);

  return (
    <>
      <div className="fixed inset-0 z-[99]" onClick={onCancel} />
      <div
        className="fixed z-[100] bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-xl shadow-xl p-3 w-56"
        style={{ left: clampedX, top: clampedY }}
      >
        <p className="text-[10px] font-semibold text-neutral-400 uppercase tracking-wide mb-2">New node</p>
        <div className="flex gap-1 mb-2.5">
          {types.map(t => (
            <button
              key={t.id}
              onClick={() => setType(t.id)}
              className={`flex-1 py-1 text-xs rounded-md font-medium border transition-colors ${
                type === t.id
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 border-neutral-200 dark:border-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <input
          ref={inputRef}
          value={label}
          onChange={e => setLabel(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Label…"
          className="w-full px-2.5 py-1.5 text-sm border border-neutral-200 dark:border-neutral-700 rounded-lg bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <div className="flex gap-1.5 mt-2">
          <button
            onClick={() => { if (label.trim()) onConfirm(type, label.trim()); }}
            disabled={!label.trim()}
            className="flex-1 py-1 text-xs rounded-md font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 transition-colors"
          >
            Add
          </button>
          <button
            onClick={onCancel}
            className="px-2 py-1 text-xs rounded-md text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </>
  );
}

// --- Main component ---
interface FmuUploadedPayload {
  filename: string;
  model_name: string;
  variables: Array<{ name: string; causality: string; variability: string; start: string; unit: string; description: string }>;
}

interface CanvasGraphProps {
  canvas: CanvasState | null | undefined;
  initialPositions?: Record<string, { x: number; y: number }>;
  onPositionsChange?: (positions: Record<string, { x: number; y: number }>) => void;
  onFmuUploaded?: (payload: FmuUploadedPayload, position?: FlowPosition) => void;
  onSimulateComplete?: (fmuNodeId: string, jobId: string, filename: string, signalNames: string[], paramValues: Record<string, string>, stopTime: number) => void;
  onDeleteNode?: (nodeId: string) => void;
  onAddNode?: (node: any, relation: { from_id: string; to_id: string; label: string } | null) => void;
  onAddEdge?: (fromId: string, toId: string, label: string, sourceHandle?: string | null, targetHandle?: string | null) => void;
  onSetNodeColor?: (nodeId: string, color: string) => void;
  workspaceDocIds?: string[];
  onAddDocToWorkspace?: (docId: string) => void;
  onRemoveDocFromWorkspace?: (docId: string) => void;
  onSetParent?: (nodeId: string, parentId: string | null, position?: FlowPosition) => void;
  onFmuFromLibrary?: (filename: string, position?: FlowPosition, parentId?: string | null) => void;
  onAddSnippet?: (
    nodes: any[],
    relations: any[],
    position?: FlowPosition,
    placements?: Array<{ id?: string; parentId: string | null; position?: FlowPosition }>
  ) => void;
  onSaveSelection?: (selectedNodeIds: string[], name?: string) => Promise<void>;
  libraryOpen?: boolean;
  onToggleLibrary?: () => void;
}

async function uploadCanvasFile(
  file: File,
  onFmuUploaded?: (payload: FmuUploadedPayload, position?: FlowPosition) => void,
  position?: FlowPosition,
) {
  if (file.name.endsWith(".fmu")) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_URL}/api/fmu/upload`, { method: "POST", body: formData });
    if (res.ok) {
      const data = await res.json();
      onFmuUploaded?.({ filename: data.filename, model_name: data.model_name, variables: data.variables ?? [] }, position);
    }
    return;
  }

  if (!KNOWLEDGE_FILE_PATTERN.test(file.name)) {
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_URL}/api/documents/upload`, { method: "POST", body: formData });
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.statusText}`);
  }
}

function CanvasGraphInner({ canvas, initialPositions = {}, onPositionsChange, onFmuUploaded, onSimulateComplete, onDeleteNode, onAddNode, onAddEdge, onSetNodeColor, workspaceDocIds, onAddDocToWorkspace, onRemoveDocFromWorkspace, onSetParent, onFmuFromLibrary, onAddSnippet, onSaveSelection, libraryOpen, onToggleLibrary }: CanvasGraphProps) {
  const { screenToFlowPosition } = useReactFlow();
  const rfContainerRef = useRef<HTMLDivElement>(null);
  const { documents, refreshDocuments, activeDocumentId, setActiveDocumentId } = useApp();
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [pdfModal, setPdfModal] = useState<PDFModalState | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [highlightedAreaId, setHighlightedAreaId] = useState<string | null>(null);
  const [previewedSource, setPreviewedSource] = useState<{ filename: string; page: number } | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const positionOverridesRef = useRef<Record<string, { x: number; y: number }>>(initialPositions);
  useEffect(() => {
    positionOverridesRef.current = { ...positionOverridesRef.current, ...initialPositions };
  }, [initialPositions]);

  const commitPositionOverrides = useCallback((
    updates: Record<string, FlowPosition>,
    freezeExisting = false,
  ) => {
    const frozen = freezeExisting
      ? Object.fromEntries(nodes.map((node) => [node.id, { ...node.position }]))
      : {};
    const next = {
      ...positionOverridesRef.current,
      ...frozen,
      ...updates,
    };
    positionOverridesRef.current = next;
    onPositionsChange?.(next);
    return next;
  }, [nodes, onPositionsChange]);

  // Tool & selection state
  const [activeTool, setActiveTool] = useState<CanvasTool>("select");
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [isSavingSnippet, setIsSavingSnippet] = useState(false);
  const [drawDraft, setDrawDraft] = useState<{
    type: NewNodeType;
    startClient: FlowPosition;
    currentClient: FlowPosition;
    startFlow: FlowPosition;
    currentFlow: FlowPosition;
  } | null>(null);
  // Snapshot of selection before a new drag-select begins (for additive / subtractive)
  const selectionSnapshot = useRef<string[]>([]);
  const modKeys = useRef<{ shift: boolean; alt: boolean }>({ shift: false, alt: false });

  useEffect(() => {
    const down = (e: KeyboardEvent) => { modKeys.current = { shift: e.shiftKey, alt: e.altKey }; };
    const up = (e: KeyboardEvent) => { modKeys.current = { shift: e.shiftKey, alt: e.altKey }; };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, []);

  const onSelectionStart = useCallback(() => {
    selectionSnapshot.current = [...selectedNodeIds];
  }, [selectedNodeIds]);

  const onSelectionChange = useCallback(({ nodes: selNodes }: { nodes: Node[]; edges: Edge[] }) => {
    const incoming = selNodes.map(n => n.id);
    const { shift, alt } = modKeys.current;
    if (shift) {
      // Shift-drag subtracts from the existing selection
      const remove = new Set(incoming);
      setSelectedNodeIds(selectionSnapshot.current.filter(id => !remove.has(id)));
    } else if (alt) {
      // Alt-drag adds incoming to the existing selection
      const merged = new Set([...selectionSnapshot.current, ...incoming]);
      setSelectedNodeIds(Array.from(merged));
    } else {
      setSelectedNodeIds(incoming);
    }
  }, []);

  // Sync selectedNodeIds back to React Flow node.selected (for additive/subtractive rendering)
  useEffect(() => {
    const selSet = new Set(selectedNodeIds);
    setNodes(nds => nds.map(n => {
      const shouldSelect = selSet.has(n.id);
      return n.selected === shouldSelect ? n : { ...n, selected: shouldSelect };
    }));
  }, [selectedNodeIds, setNodes]);

  const handleSaveSnippet = useCallback(async () => {
    if (!onSaveSelection || selectedNodeIds.length === 0) return;
    setIsSavingSnippet(true);
    await onSaveSelection(selectedNodeIds);
    setIsSavingSnippet(false);
  }, [onSaveSelection, selectedNodeIds]);

  // Context menu (right-click on node)
  const [contextMenu, setContextMenu] = useState<{
    nodeId: string;
    top?: number | false; left?: number | false;
    right?: number | false; bottom?: number | false;
  } | null>(null);

  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault();
    const pane = rfContainerRef.current?.getBoundingClientRect();
    if (!pane) return;
    setContextMenu({
      nodeId: node.id,
      top:    event.clientY - pane.top  < pane.height - 160 ? event.clientY - pane.top  : false,
      left:   event.clientX - pane.left < pane.width  - 180 ? event.clientX - pane.left : false,
      right:  event.clientX - pane.left >= pane.width  - 180 ? pane.width  - (event.clientX - pane.left) : false,
      bottom: event.clientY - pane.top  >= pane.height - 160 ? pane.height - (event.clientY - pane.top)  : false,
    });
  }, []);

  // New-node popup (drag-from-handle or double-click on pane)
  const [newNodePopup, setNewNodePopup] = useState<{
    screenX: number; screenY: number; flowX: number; flowY: number; sourceId: string | null;
  } | null>(null);
  const onConnectEnd = useCallback((event: MouseEvent | TouchEvent, connectionState: any) => {
    // Only show picker when dropped on empty canvas (not on a valid handle)
    if (connectionState?.isValid || !connectionState?.fromNode) return;
    const sourceId = connectionState.fromNode.id as string;
    const clientX = 'changedTouches' in event ? (event as TouchEvent).changedTouches[0]!.clientX : (event as MouseEvent).clientX;
    const clientY = 'changedTouches' in event ? (event as TouchEvent).changedTouches[0]!.clientY : (event as MouseEvent).clientY;
    const pos = screenToFlowPosition({ x: clientX, y: clientY });
    setNewNodePopup({ screenX: clientX, screenY: clientY, flowX: pos.x, flowY: pos.y, sourceId });
  }, [screenToFlowPosition]);

  const onConnectStart = useCallback(() => {}, []);

  const onConnect = useCallback((params: any) => {
    if (params.source && params.target) {
      onAddEdge?.(params.source, params.target, '', params.sourceHandle ?? null, params.targetHandle ?? null);
    }
  }, [onAddEdge]);

  const handleCanvasMouseDown = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!isInsertTool(activeTool) || event.button !== 0) return;
    const target = event.target as Element;
    if (!target.closest('.react-flow__pane')) return;
    event.preventDefault();
    event.stopPropagation();
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setContextMenu(null);
    setNewNodePopup(null);
    setSelectedNodeIds([]);
    setDrawDraft({
      type: activeTool,
      startClient: { x: event.clientX, y: event.clientY },
      currentClient: { x: event.clientX, y: event.clientY },
      startFlow: flowPos,
      currentFlow: flowPos,
    });
  }, [activeTool, screenToFlowPosition]);

  const onPaneDoubleClick = useCallback((event: React.MouseEvent) => {
    if (isInsertTool(activeTool)) return;
    const target = event.target as Element;
    // Only trigger on the canvas pane background, not on nodes/handles/controls
    if (!target.closest('.react-flow__pane') || target.closest('.react-flow__node') || target.closest('.react-flow__controls')) return;
    const pos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setNewNodePopup({ screenX: event.clientX, screenY: event.clientY, flowX: pos.x, flowY: pos.y, sourceId: null });
  }, [activeTool, screenToFlowPosition]);

  const _makeNode = useCallback((type: NewNodeType, label: string, flowPos: { x: number; y: number }) => {
    const id = `user_${type}_${Date.now()}`;
    const node: any = {
      id, node_type: type, status: 'found',
      title: (type !== 'fact' && type !== 'funnel' && type !== 'area') ? label : '',
      text: type === 'fact' ? label : '',
      spec_title: '', properties: [], last_updated_run_id: '',
      filename: '', page: 0, bbox: [], highlights: [],
      fmu_filename: '', fmu_model_name: '', fmu_variables: [], fmu_param_values: {},
      plot_job_id: '', plot_fmu_filename: '', plot_signal_names: [], plot_stop_time: 10,
      funnel_label: type === 'funnel' ? (label || 'Funnel') : '',
      area_label: type === 'area' ? (label || 'Area') : '',
      area_width: type === 'area' ? 600 : 0,
      area_height: type === 'area' ? 400 : 0,
      width: NODE_SIZE[
        type === 'funnel' ? 'funnelNode'
        : type === 'area' ? 'areaNode'
        : type === 'fact' ? 'factNode'
        : type === 'entity' ? 'entityNode'
        : 'conceptNode'
      ]?.w ?? 220,
      height: NODE_SIZE[
        type === 'funnel' ? 'funnelNode'
        : type === 'area' ? 'areaNode'
        : type === 'fact' ? 'factNode'
        : type === 'entity' ? 'entityNode'
        : 'conceptNode'
      ]?.h ?? 80,
      parent_id: '',
    };
    positionOverridesRef.current[id] = flowPos;
    return { id, node };
  }, []);

  const createToolbarNode = useCallback((type: NewNodeType, startFlow: FlowPosition, currentFlow: FlowPosition) => {
    const draftLeft = Math.min(startFlow.x, currentFlow.x);
    const draftTop = Math.min(startFlow.y, currentFlow.y);
    const draftWidth = Math.abs(currentFlow.x - startFlow.x);
    const draftHeight = Math.abs(currentFlow.y - startFlow.y);
    const nodeSize =
      type === "funnel" ? NODE_SIZE.funnelNode!
      : type === "area" ? NODE_SIZE.areaNode!
      : type === "fact" ? NODE_SIZE.factNode!
      : type === "entity" ? NODE_SIZE.entityNode!
      : NODE_SIZE.conceptNode!;
    const center = {
      x: draftLeft + Math.max(draftWidth, nodeSize.w) / 2,
      y: draftTop + Math.max(draftHeight, nodeSize.h) / 2,
    };
    const basePosition = type === "area"
      ? { x: draftLeft, y: draftTop }
      : anchorAtCenter(center, nodeSize);
    const label = type === 'fact' ? 'New note' : `New ${type}`;
    const { id, node } = _makeNode(type, label, basePosition);
    if (type === "area") {
      node.area_width = Math.max(260, draftWidth || nodeSize.w);
      node.area_height = Math.max(180, draftHeight || nodeSize.h);
      node.width = node.area_width;
      node.height = node.area_height;
    } else {
      node.width = Math.max(nodeSize.w, draftWidth || nodeSize.w);
      node.height = Math.max(nodeSize.h, draftHeight || nodeSize.h);
    }
    commitPositionOverrides({ [id]: basePosition }, true);
    onAddNode?.(node, null);
    setActiveTool("select");
  }, [_makeNode, commitPositionOverrides, onAddNode]);

  useEffect(() => {
    if (!drawDraft) return;
    const handleMove = (event: MouseEvent) => {
      setDrawDraft((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          currentClient: { x: event.clientX, y: event.clientY },
          currentFlow: screenToFlowPosition({ x: event.clientX, y: event.clientY }),
        };
      });
    };
    const handleUp = () => {
      setDrawDraft((prev) => {
        if (!prev) return prev;
        createToolbarNode(prev.type, prev.startFlow, prev.currentFlow);
        return null;
      });
    };
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp, { once: true });
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [drawDraft, createToolbarNode, screenToFlowPosition]);

  const handleNewNodeConfirm = useCallback((type: NewNodeType, label: string) => {
    if (!newNodePopup) return;
    const { id, node } = _makeNode(type, label, { x: newNodePopup.flowX, y: newNodePopup.flowY });
    commitPositionOverrides({ [id]: { x: newNodePopup.flowX, y: newNodePopup.flowY } }, true);
    onAddNode?.(node, newNodePopup.sourceId ? { from_id: newNodePopup.sourceId, to_id: id, label: '' } : null);
    setActiveTool("select");
    setNewNodePopup(null);
  }, [newNodePopup, _makeNode, commitPositionOverrides, onAddNode]);

  // Keep fresh refs for use inside effects without adding to deps
  const documentsRef = useRef(documents);
  const activeDocumentIdRef = useRef(activeDocumentId);
  const setActiveDocumentIdRef = useRef(setActiveDocumentId);
  const nodesRef = useRef(nodes);
  const relationsRef = useRef<Relation[]>([]);
  useEffect(() => { documentsRef.current = documents; }, [documents]);
  useEffect(() => { activeDocumentIdRef.current = activeDocumentId; }, [activeDocumentId]);
  useEffect(() => { setActiveDocumentIdRef.current = setActiveDocumentId; }, [setActiveDocumentId]);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);

  const updateAreaHighlight = useCallback((absolutePosition: FlowPosition, size: { w: number; h: number }, excludeNodeId?: string) => {
    const bestParent = findBestAreaParent(absolutePosition, size, nodesRef.current, excludeNodeId);
    setHighlightedAreaId(bestParent?.id ?? null);
    return bestParent;
  }, []);

  // Track drag state for parent-moves-children behaviour
  const dragStartRef = useRef<{
    nodeId: string;
    startPos: { x: number; y: number };
    descendantStartPos: Map<string, { x: number; y: number }>;
  } | null>(null);

  const onNodeDragStart = useCallback((_evt: React.MouseEvent, node: Node) => {
    // Build children map — exclude evidence edges so doc nodes don't get dragged
    const childrenOf = new Map<string, string[]>();
    for (const r of relationsRef.current) {
      if (r.to_id.startsWith('__doc_')) continue;
      const arr = childrenOf.get(r.from_id) ?? [];
      arr.push(r.to_id);
      childrenOf.set(r.from_id, arr);
    }
    const descIds = descendants([node.id], childrenOf);
    const descendantStartPos = new Map<string, { x: number; y: number }>();
    for (const n of nodesRef.current) {
      if (descIds.has(n.id)) descendantStartPos.set(n.id, { ...n.position });
    }
    dragStartRef.current = { nodeId: node.id, startPos: { ...node.position }, descendantStartPos };
    setHighlightedAreaId(null);
  }, []);

  const onNodeDrag = useCallback((_evt: React.MouseEvent, node: Node) => {
    const drag = dragStartRef.current;
    const currentParentNode = node.parentId
      ? nodesRef.current.find((candidate) => candidate.id === node.parentId)
      : null;
    const absolutePosition = currentParentNode
      ? { x: currentParentNode.position.x + node.position.x, y: currentParentNode.position.y + node.position.y }
      : { ...node.position };
    updateAreaHighlight(absolutePosition, inferNodeSize(node), node.id);
    if (!drag || drag.nodeId !== node.id || drag.descendantStartPos.size === 0) return;
    const dx = node.position.x - drag.startPos.x;
    const dy = node.position.y - drag.startPos.y;
    setNodes((nds) =>
      nds.map((n) => {
        const sp = drag.descendantStartPos.get(n.id);
        if (!sp) return n;
        return { ...n, position: { x: sp.x + dx, y: sp.y + dy } };
      })
    );
  }, [setNodes, updateAreaHighlight]);

  const handleArrangeCanvas = useCallback(() => {
    const arranged = applyMindmapLayout(
      nodesRef.current.map((node) => ({ ...node, position: { ...node.position } })),
      edges.map((edge) => ({ ...edge })),
    );
    const updates = Object.fromEntries(arranged.map((node) => [node.id, { ...node.position }]));
    commitPositionOverrides(updates);
    setNodes(arranged);
  }, [edges, commitPositionOverrides, setNodes]);

  const selectedCanvasItem = useMemo<CanvasItem | null>(() => {
    if (selectedNodeIds.length !== 1) return null;
    const selected = nodes.find((node) => node.id === selectedNodeIds[0]);
    return ((selected?.data as any)?.node ?? (selected?.data as any)?.item ?? null) as CanvasItem | null;
  }, [nodes, selectedNodeIds]);

  const onNodeDragStop = useCallback((_evt: React.MouseEvent, node: Node) => {
    // Record final positions for the dragged node and all its descendants
    const drag = dragStartRef.current;
    const updates: Record<string, { x: number; y: number }> = { [node.id]: { ...node.position } };
    if (drag && drag.nodeId === node.id) {
      const dx = node.position.x - drag.startPos.x;
      const dy = node.position.y - drag.startPos.y;
      drag.descendantStartPos.forEach((sp, id) => {
        updates[id] = { x: sp.x + dx, y: sp.y + dy };
      });
    }
    dragStartRef.current = null;
    setHighlightedAreaId(null);
    commitPositionOverrides(updates);

    // Detect area containment: if more than 50% of a node overlaps an area, parent it
    if (node.type !== 'areaNode' && onSetParent) {
      const currentParent = node.parentId ?? null;
      const nodeSize = inferNodeSize(node);
      const currentParentNode = currentParent
        ? nodesRef.current.find((candidate) => candidate.id === currentParent)
        : null;
      const absolutePosition = currentParentNode
        ? {
            x: currentParentNode.position.x + node.position.x,
            y: currentParentNode.position.y + node.position.y,
          }
        : { ...node.position };
      const bestParent = findBestAreaParent(absolutePosition, nodeSize, nodesRef.current, node.id);
      const newParent = bestParent?.id ?? null;
      if (newParent !== currentParent) {
        onSetParent(
          node.id,
          newParent,
          bestParent?.position ?? absolutePosition,
        );
      }
    }
  }, [commitPositionOverrides, onSetParent]);

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

  const onNodeDoubleClick = useCallback((_evt: React.MouseEvent, node: Node) => {
    const canvasNode = nodesRef.current.find((n: Node) => n.id === node.id);
    const nodeType = canvasNode
      ? (canvasNode.data as any)?.node?.semanticType ?? (canvasNode.data as any)?.node?.node_type ?? (canvasNode.data as any)?.node_type
      : undefined;
    if (!nodeType || !isCollapsibleNodeType(nodeType)) return;
    handleToggleCollapse(node.id);
  }, [handleToggleCollapse]);

  const [simulateError, setSimulateError] = useState<string | null>(null);

  const handleSimulate = useCallback(async (nodeId: string, filename: string, paramValues: Record<string, string>, stopTime: number) => {
    setSimulateError(null);
    const overrides: Record<string, number> = {};
    Object.entries(paramValues).forEach(([k, v]) => {
      const n = parseFloat(v);
      if (!isNaN(n)) overrides[k] = n;
    });
    try {
      const res = await fetch(`${API_URL}/api/fmu/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, param_overrides: overrides, stop_time: stopTime }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        setSimulateError(body.detail ?? 'Simulation failed');
        return;
      }
      const { job_id } = await res.json();
      const fmuNode = canvas?.nodes.find((n: any) => n.id === nodeId);
      const signalNames: string[] = (fmuNode?.fmu_variables ?? [])
        .filter((v: any) => v.causality === 'output')
        .map((v: any) => v.name);
      onSimulateComplete?.(nodeId, job_id, filename, signalNames, paramValues, stopTime);
    } catch (e: any) {
      setSimulateError(e?.message ?? 'Simulation failed');
    }
  }, [canvas, onSimulateComplete]);

  const rawNodes = (canvas?.nodes ?? []) as LegacyCanvasNode[];
  const canvasItems = useMemo(() => rawNodes.map(adaptLegacyNodeToCanvasItem), [rawNodes]);
  const explicitRelations = canvas?.relations ?? [];
  const relations = useMemo(
    () => [...explicitRelations, ...buildDerivedEvidenceRelations(canvasItems, explicitRelations, documents)],
    [canvasItems, explicitRelations, documents],
  );
  relationsRef.current = relations;

  // Structural key — re-layout only when nodes/edges are added or removed,
  // not when content/status changes (so in-progress updates don't jump)
  const structureKey = useMemo(
    () =>
      rawNodes.map((n) => n.id).join(",") +
      "|" +
      relations.map((r) => `${r.from_id}>${r.to_id}`).join(",") +
      "|" +
      [...collapsedIds].sort().join(",") +
      "|docs:" +
      documents.map((d) => d.document_id).join(",") +
      "|workspace:" + (workspaceDocIds ?? []).join(",") +
      "|active:" + (activeDocumentId ?? ""),
    [rawNodes, relations, collapsedIds, documents, workspaceDocIds, activeDocumentId]
  );

  // Build document nodes from current KB documents
  // Refs used by the debounced layout effect
  const layoutKeyRef = useRef<string>('');
  const isFirstLayout = useRef(true);

  useEffect(() => {
    layoutKeyRef.current = structureKey;
    // Always debounce — including the first layout.
    // Using delay=0 on the first layout caused streaming thrash: intermediate partial
    // graphs (e.g. concept + topics before facts/edges arrive) got laid out by Dagre
    // and spread wide before settling. 400 ms is imperceptible on load but eliminates
    // the spread-then-collapse animation during agent streaming.
    const delay = 400;

    const timer = setTimeout(() => {
      if (layoutKeyRef.current !== structureKey) return; // a newer layout superseded this one

    if (canvasItems.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const nodeMap = new Map(canvasItems.map((n) => [n.id, n]));

    // Build children map
    const childrenOf = new Map<string, string[]>();
    for (const r of relations) {
      const arr = childrenOf.get(r.from_id) ?? [];
      arr.push(r.to_id);
      childrenOf.set(r.from_id, arr);
    }

    const hiddenIds = descendants([...collapsedIds], childrenOf);

    // Build RF nodes (no position yet — dagre will assign them)
    const rfNodes: Node[] = canvasItems.map((n) => {
      const hidden = hiddenIds.has(n.id);

      if (isCollapsibleNodeType(n.semanticType)) {
        return applyExplicitNodeSize(n, buildFlowNode(
          n.id,
          COLLAPSIBLE_NODE_COMPONENTS[n.semanticType],
          n.color,
          hidden,
          buildCollapsibleNodeData(n, childrenOf, collapsedIds, handleToggleCollapse, onDeleteNode),
        ), n.semanticType === "entity" ? NODE_SIZE.entityNode! : n.semanticType === "topic" ? NODE_SIZE.topicNode! : n.semanticType === "category" ? NODE_SIZE.categoryNode! : NODE_SIZE.conceptNode!);
      }
      if (n.semanticType === "fact") {
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "factNode", n.color, hidden, {
          node: n,
          onOpenPDF: handleOpenPDF,
          onPreviewSource: (filename: string | null, page?: number | null) => setPreviewedSource(filename && page ? { filename, page } : null),
          onDelete: onDeleteNode,
          ...getEvidenceData(n.id, relations, documentsRef.current),
        }), NODE_SIZE.factNode!);
      }
      if (n.semanticType === "spec") {
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "specNode", n.color, hidden, {
          node: n,
          onOpenPDF: handleOpenPDF,
          onPreviewSource: (filename: string | null, page?: number | null) => setPreviewedSource(filename && page ? { filename, page } : null),
          onDelete: onDeleteNode,
          ...getEvidenceData(n.id, relations, documentsRef.current),
        }), NODE_SIZE.specNode!);
      }
      if (n.semanticType === "document") {
        const doc = documentsRef.current.find((item) => item.document_id === n.id.replace(/^__doc_/, ""));
        const evidenceCount = relations.filter(r => r.to_id === n.id).length;
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "documentNode", n.color, hidden, {
          item: doc ? adaptDocumentToCanvasItem(doc) : n,
          doc,
          isActive: doc?.document_id === activeDocumentIdRef.current,
          previewPage: previewedSource && previewedSource.filename === doc?.filename ? previewedSource.page : null,
          onActivate: (id: string) => setActiveDocumentIdRef.current(id || null),
          onOpenPDF: handleOpenPDF,
          onRemoveFromCanvas: onRemoveDocFromWorkspace,
          evidenceCount,
        } satisfies DocumentNodeData), NODE_SIZE.documentNode!);
      }
      if (n.semanticType === "image") {
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "imageNode", n.color, hidden, {
          node: n,
          onOpenPDF: handleOpenPDF,
          onDelete: onDeleteNode,
        }), NODE_SIZE.imageNode!);
      }
      if (n.semanticType === "fmu") {
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "fmuNode", n.color, hidden, {
          node: n,
          onSimulate: handleSimulate,
          onDelete: onDeleteNode,
        } satisfies FmuNodeData), NODE_SIZE.fmuNode!);
      }
      if (n.semanticType === "plot") {
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "plotNode", n.color, hidden, {
          node: n,
          onDelete: onDeleteNode,
        } satisfies PlotNodeData), NODE_SIZE.plotNode!);
      }
      if (n.semanticType === "funnel") {
        const connectedDocCount = relations.filter(r => r.to_id === n.id && r.from_id.startsWith('__doc_')).length;
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "funnelNode", n.color, hidden, {
          node: n,
          onDelete: onDeleteNode,
          connectedDocCount,
        } satisfies FunnelNodeData), NODE_SIZE.funnelNode!);
      }
      if (n.semanticType === "area") {
        const connectedSourceNames = relations
          .filter(r => r.to_id === n.id)
          .map(r => {
            const srcNode = nodeMap.get(r.from_id);
            if (r.from_id.startsWith('__doc_')) {
              const doc = documentsRef.current.find(d => `__doc_${d.document_id}` === r.from_id);
              return doc?.filename ?? r.from_id;
            }
            return srcNode?.funnel_label || srcNode?.title || r.from_id;
          });
        const areaNode = applyExplicitNodeSize(n, buildFlowNode(n.id, "areaNode", n.color, hidden, {
          node: n,
          onDelete: onDeleteNode,
          connectedSourceNames,
          highlighted: highlightedAreaId === n.id,
        } satisfies AreaNodeData), NODE_SIZE.areaNode!);
        areaNode.style = {
          ...areaNode.style,
          width: n.width || n.area_width || 600,
          height: n.height || n.area_height || 400,
          zIndex: -1,
        };
        return areaNode;
      }
      // backward-compat: source/entity/category fallback
      return buildFlowNode(n.id, "sourceNode", n.color, hidden, {
        node: n,
        onOpenPDF: handleOpenPDF,
      });
    });

    // Set parentId on nodes that belong to an area, and sort areas first (RF requirement)
    const parentMap = new Map<string, string>();
    for (const n of canvasItems) {
      if (n.parentId) parentMap.set(n.id, n.parentId);
    }
    for (const rfn of rfNodes) {
      const pid = parentMap.get(rfn.id);
      if (pid) {
        rfn.parentId = pid;
      }
    }
    // Areas must appear before their children in the array
    rfNodes.sort((a, b) => {
      const aIsArea = a.type === 'areaNode' ? 0 : 1;
      const bIsArea = b.type === 'areaNode' ? 0 : 1;
      return aIsArea - bIsArea;
    });

    // Compute source provenance and color map for edges
    const sourceColorMap = buildSourceColorMap(workspaceDocIds ?? []);
    const nodeSources = computeNodeSources(
      canvasItems.map(n => ({ id: n.id, parent_id: n.parentId })),
      relations,
    );

    const rfEdges: Edge[] = relations.map((r, idx) => {
      const fromNode = nodeMap.get(r.from_id);
      const toNode = nodeMap.get(r.to_id);
      const isConceptTopic = fromNode?.semanticType === "concept";
      const isEntityCat = fromNode?.semanticType === "entity";
      const isCatTopic  = fromNode?.semanticType === "category";
      const isTopicFact = (fromNode?.semanticType === "topic" || fromNode?.semanticType === "category") && toNode?.semanticType === "fact";
      const isSpec      = toNode?.semanticType === "spec";
      const isEvidence  = r.to_id.startsWith('__doc_');
      const isSimPlot   = fromNode?.semanticType === "fmu" && toNode?.semanticType === "plot";
      // Hide evidence edges that originate from leaf nodes (fact/spec) — replaced by
      // deduplicated topic→doc reference lines added below.
      // Source-colored edges: if the source node has provenance, use its color
      const provenanceColor = !isEvidence
        ? pickEdgeSourceColor(nodeSources.get(r.from_id), sourceColorMap)
        : null;

      const strokeColor = provenanceColor
        ? provenanceColor
        : isSimPlot    ? "#14b8a6"
        : isConceptTopic ? "#8b5cf6"
        : isEntityCat ? "#64748b"
        : isCatTopic  ? "#3b82f6"
        : isTopicFact ? "#f59e0b"
        : isSpec       ? "#8b5cf6"
        : isEvidence   ? "#94a3b8"
        : "#6366f1";
      const renderedSource = isEvidence ? r.to_id : r.from_id;
      const renderedTarget = isEvidence ? r.from_id : r.to_id;
      const renderedSourceHandle = isEvidence ? (r.target_handle || undefined) : (r.source_handle || undefined);
      const renderedTargetHandle = isEvidence ? (r.source_handle || undefined) : (r.target_handle || undefined);
      const usesAnchoredHandles = !!(renderedSourceHandle || renderedTargetHandle);
      return {
        id: `e-${idx}`,
        source: renderedSource,
        target: renderedTarget,
        sourceHandle: renderedSourceHandle,
        targetHandle: renderedTargetHandle,
        label: r.label || undefined,
        type: usesAnchoredHandles ? "anchored" : "floating",
        hidden: hiddenIds.has(renderedSource) || hiddenIds.has(renderedTarget),
        animated: isEvidence || isConceptTopic || isEntityCat || isCatTopic,
        style: {
          stroke: strokeColor,
          strokeWidth: isEntityCat ? 3.5 : isConceptTopic || isCatTopic ? 3 : isTopicFact || isSpec ? 2.5 : isEvidence ? 1.8 : 2,
          strokeDasharray: isEvidence || isSpec ? "5 4" : undefined,
          opacity: isEvidence ? 0.72 : undefined,
        },
        labelStyle: { fill: isSimPlot ? "#0f766e" : "#6366f1", fontWeight: 600, fontSize: 10 },
        labelBgStyle: { fill: isSimPlot ? "#f0fdfa" : "#f5f3ff", fillOpacity: 0.92 },
        labelBgPadding: [3, 2] as [number, number],
      };
    });

    // Build parent lookup (excluding evidence edges) for default manual placement
    const parentOf = new Map<string, string>();
    for (const r of relations) {
      if (!r.to_id.startsWith('__doc_')) parentOf.set(r.to_id, r.from_id);
    }
    const existingNodePositions = new Map(nodesRef.current.map((node) => [node.id, node.position]));
    const manuallyPlaced = placeNodesManually(
      rfNodes,
      parentOf,
      positionOverridesRef.current,
      existingNodePositions,
    );
    setNodes(manuallyPlaced);
    setEdges(rfEdges);
    if (isFirstLayout.current) isFirstLayout.current = false;
    }, delay);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structureKey]);

  // Update node data (status, content) without re-layouting
  useEffect(() => {
    if (canvasItems.length === 0) return;
    const nodeMap = new Map(canvasItems.map((n) => [n.id, n]));
    const childrenOf = new Map<string, string[]>();
    for (const r of relations) {
      const arr = childrenOf.get(r.from_id) ?? [];
      arr.push(r.to_id);
      childrenOf.set(r.from_id, arr);
    }

    setNodes((prev) =>
      prev.map((rfNode) => {
        const n = nodeMap.get(rfNode.id);
        if (!n) return rfNode;
        if (isCollapsibleNodeType(n.semanticType)) {
          return {
            ...rfNode,
            data: {
              ...rfNode.data,
              ...buildCollapsibleNodeData(n, childrenOf, collapsedIds, handleToggleCollapse, onDeleteNode),
            },
          };
        }
        if (n.semanticType === "fact" || n.semanticType === "spec") {
          return {
            ...rfNode,
            data: {
              ...rfNode.data,
              node: n,
              onOpenPDF: handleOpenPDF,
              onPreviewSource: (filename: string | null, page?: number | null) => setPreviewedSource(filename && page ? { filename, page } : null),
              onDelete: onDeleteNode,
              ...getEvidenceData(n.id, relations, documentsRef.current),
            },
          };
        }
        if (n.semanticType === "document") {
          const doc = documentsRef.current.find((item) => item.document_id === n.id.replace(/^__doc_/, ""));
          return {
            ...rfNode,
            data: {
              ...rfNode.data,
              item: doc ? adaptDocumentToCanvasItem(doc) : n,
              doc,
              isActive: doc?.document_id === activeDocumentIdRef.current,
              previewPage: previewedSource && previewedSource.filename === doc?.filename ? previewedSource.page : null,
              onActivate: (id: string) => setActiveDocumentIdRef.current(id || null),
              onOpenPDF: handleOpenPDF,
              onRemoveFromCanvas: onRemoveDocFromWorkspace,
              evidenceCount: relations.filter(r => r.to_id === n.id).length,
            },
          };
        }
        if (n.semanticType === "fmu") {
          return { ...rfNode, data: { ...rfNode.data, node: n, onSimulate: handleSimulate } };
        }
        if (n.semanticType === "plot") {
          return { ...rfNode, data: { ...rfNode.data, node: n } };
        }
        if (n.semanticType === "image") {
          return { ...rfNode, data: { ...rfNode.data, node: n, onOpenPDF: handleOpenPDF, onDelete: onDeleteNode } };
        }
        return { ...rfNode, data: { ...rfNode.data, node: n } };
      })
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvasItems, relations, onRemoveDocFromWorkspace, previewedSource]);

  // File drop handlers
  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    const t = e.dataTransfer.types;
    const hasFiles = t.includes("Files");
    const hasLibItem = t.includes("application/anchor-doc") || t.includes("application/anchor-fmu") || t.includes("application/anchor-snippet");
    const hasNodeType = t.includes("application/anchor-nodetype");
    if (!hasFiles && !hasLibItem && !hasNodeType) return;
    e.preventDefault();
    setIsDraggingOver(hasFiles || hasLibItem);
    const absolutePosition = screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const nodeType = e.dataTransfer.getData("application/anchor-nodetype") as NewNodeType | '';
    const fmuFilename = e.dataTransfer.getData("application/anchor-fmu");
    const docId = e.dataTransfer.getData("application/anchor-doc");
    const snippetPayload = e.dataTransfer.getData("application/anchor-snippet");
    const size =
      nodeType === "funnel" ? NODE_SIZE.funnelNode
      : nodeType === "area" ? null
      : nodeType === "fact" ? NODE_SIZE.factNode
      : nodeType === "entity" ? NODE_SIZE.entityNode
      : nodeType === "concept" ? NODE_SIZE.conceptNode
      : fmuFilename ? NODE_SIZE.fmuNode
      : docId ? DOCUMENT_NODE_SIZE
      : snippetPayload ? { w: 220, h: 84 }
      : hasFiles ? DOCUMENT_NODE_SIZE
      : null;
    if (size) {
      updateAreaHighlight(anchorAtCenter(absolutePosition, size), size);
    } else {
      setHighlightedAreaId(null);
    }
  }, [screenToFlowPosition, updateAreaHighlight]);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Element | null)) {
      setIsDraggingOver(false);
      setHighlightedAreaId(null);
    }
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingOver(false);
    setHighlightedAreaId(null);

    // Handle toolbar node-type drops
    const nodeType = e.dataTransfer.getData("application/anchor-nodetype") as NewNodeType | '';
    if (nodeType) {
      const nodeSize =
        nodeType === "funnel" ? NODE_SIZE.funnelNode!
        : nodeType === "area" ? NODE_SIZE.areaNode!
        : nodeType === "fact" ? NODE_SIZE.factNode!
        : nodeType === "entity" ? NODE_SIZE.entityNode!
        : NODE_SIZE.conceptNode!;
      const absolutePos = anchorAtCenter(
        screenToFlowPosition({ x: e.clientX, y: e.clientY }),
        nodeSize,
      );
      const areaParent = nodeType === "area"
        ? null
        : findBestAreaParent(absolutePos, nodeSize, nodesRef.current);
      const pos = areaParent?.position ?? absolutePos;
      const label = nodeType === 'fact' ? 'New fact' : `New ${nodeType}`;
      const { id, node } = _makeNode(nodeType, label, pos);
      if (areaParent) node.parent_id = areaParent.id;
      commitPositionOverrides({ [id]: pos }, true);
      onAddNode?.(node, null);
      return;
    }

    // Handle library drawer drops (doc or fmu already on server)
    const dropPos = screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const docId = e.dataTransfer.getData("application/anchor-doc");
    const fmuFilename = e.dataTransfer.getData("application/anchor-fmu");
    const snippetPayload = e.dataTransfer.getData("application/anchor-snippet");
    if (docId) {
      const docPos = anchorAtCenter(dropPos, DOCUMENT_NODE_SIZE);
      commitPositionOverrides({ [`__doc_${docId}`]: docPos }, true);
      onAddDocToWorkspace?.(docId);
      return;
    }
    if (fmuFilename) {
      const absolutePos = anchorAtCenter(dropPos, NODE_SIZE.fmuNode!);
      const areaParent = findBestAreaParent(absolutePos, NODE_SIZE.fmuNode!, nodesRef.current);
      const finalPos = areaParent?.position ?? absolutePos;
      commitPositionOverrides({}, true);
      onFmuFromLibrary?.(fmuFilename, finalPos, areaParent?.id ?? null);
      return;
    }
    if (snippetPayload) {
      try {
        const parsed = JSON.parse(snippetPayload);
        const snippetBasePos = { x: dropPos.x, y: dropPos.y };
        const sourcePositions = Array.isArray(parsed.nodes)
          ? parsed.nodes.map((n: any, index: number) => ({
              id: n?.id,
              position: n?.position && typeof n.position.x === "number" && typeof n.position.y === "number"
                ? n.position
                : { x: (index % 3) * 260, y: Math.floor(index / 3) * 160 },
            }))
          : [];
        const xs = sourcePositions.map((item: any) => item.position.x);
        const ys = sourcePositions.map((item: any) => item.position.y);
        const centerX = xs.length > 0 ? (Math.min(...xs) + Math.max(...xs)) / 2 : 0;
        const centerY = ys.length > 0 ? (Math.min(...ys) + Math.max(...ys)) / 2 : 0;
        const placements = sourcePositions.map((item: any, index: number) => {
          const absolutePosition = {
            x: item.position.x - centerX + snippetBasePos.x,
            y: item.position.y - centerY + snippetBasePos.y,
          };
          const rawNode = parsed.nodes?.[index];
          const size =
            rawNode?.node_type === "fmu" ? NODE_SIZE.fmuNode!
            : rawNode?.node_type === "plot" ? NODE_SIZE.plotNode!
            : rawNode?.node_type === "image" ? NODE_SIZE.imageNode!
            : rawNode?.node_type === "funnel" ? NODE_SIZE.funnelNode!
            : rawNode?.node_type === "area" ? NODE_SIZE.areaNode!
            : rawNode?.node_type === "spec" ? NODE_SIZE.specNode!
            : rawNode?.node_type === "entity" ? NODE_SIZE.entityNode!
            : rawNode?.node_type === "topic" ? NODE_SIZE.topicNode!
            : rawNode?.node_type === "concept" ? NODE_SIZE.conceptNode!
            : NODE_SIZE.factNode!;
          const areaParent = rawNode?.node_type === "area"
            ? null
            : findBestAreaParent(absolutePosition, size, nodesRef.current);
          return {
            id: item.id,
            parentId: areaParent?.id ?? null,
            position: areaParent?.position ?? absolutePosition,
          };
        });
        commitPositionOverrides({}, true);
        onAddSnippet?.(parsed.nodes ?? [], parsed.relations ?? [], dropPos, placements);
      } catch {
        // ignore malformed snippet payload
      }
      return;
    }

    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;
    try {
      commitPositionOverrides({}, true);
      await Promise.all(files.map((file, index) => uploadCanvasFile(
        file,
        onFmuUploaded,
        anchorAtCenter(
          {
            x: dropPos.x + index * 36,
            y: dropPos.y + index * 28,
          },
          file.name.endsWith(".fmu") ? NODE_SIZE.fmuNode! : DOCUMENT_NODE_SIZE,
        ),
      )));
      refreshDocuments();
    } catch {
      // upload failed — user can retry; suppress to avoid dev overlay noise
    }
  }, [onAddDocToWorkspace, onAddNode, onAddSnippet, onFmuFromLibrary, onFmuUploaded, refreshDocuments, screenToFlowPosition, _makeNode, commitPositionOverrides]);

  return (
    <>
      <div
        ref={rfContainerRef}
        className={`w-full h-full overflow-hidden relative ${
          isInsertTool(activeTool) || activeTool === "connect"
            ? "cursor-crosshair"
            : "cursor-default"
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onMouseDown={handleCanvasMouseDown}
        onDoubleClick={onPaneDoubleClick}
      >
        <LeftToolRail
          activeTool={activeTool}
          onChange={setActiveTool}
          onArrange={handleArrangeCanvas}
          onToggleLibrary={onToggleLibrary}
          libraryOpen={libraryOpen}
        />
        {selectedCanvasItem && (
          <SelectionInspector
            node={selectedCanvasItem}
            onSetColor={onSetNodeColor}
            onDelete={(nodeId) => {
              if (nodeId.startsWith("__doc_")) onRemoveDocFromWorkspace?.(nodeId.replace(/^__doc_/, ""));
              else onDeleteNode?.(nodeId);
            }}
          />
        )}
        {activeTool === "connect" && (
          <div className="absolute left-1/2 top-16 z-20 -translate-x-1/2 rounded-full border border-neutral-200/80 bg-white/90 px-3 py-1 text-[11px] text-neutral-500 shadow-sm backdrop-blur-md dark:border-neutral-700/80 dark:bg-neutral-900/90 dark:text-neutral-400">
            Drag from node handles to connect items
          </div>
        )}
        {isInsertTool(activeTool) && (
          <div className="absolute left-1/2 top-16 z-20 -translate-x-1/2 rounded-full border border-neutral-200/80 bg-white/90 px-3 py-1 text-[11px] text-neutral-500 shadow-sm backdrop-blur-md dark:border-neutral-700/80 dark:bg-neutral-900/90 dark:text-neutral-400">
            Click and drag on the canvas to create a {activeTool}
          </div>
        )}
        {drawDraft && (
          <div
            className={`absolute z-20 pointer-events-none rounded-2xl border-2 ${
              drawDraft.type === "area"
                ? "border-dashed border-indigo-500 bg-indigo-100/30 dark:bg-indigo-900/20"
                : drawDraft.type === "funnel"
                ? "border-teal-500 bg-teal-100/30 dark:bg-teal-900/20"
                : drawDraft.type === "entity"
                ? "border-slate-500 bg-slate-100/30 dark:bg-slate-900/20"
                : drawDraft.type === "fact"
                ? "border-amber-500 bg-amber-100/30 dark:bg-amber-900/20"
                : "border-violet-500 bg-violet-100/30 dark:bg-violet-900/20"
            }`}
            style={{
              left: Math.min(drawDraft.startClient.x, drawDraft.currentClient.x) - (rfContainerRef.current?.getBoundingClientRect().left ?? 0),
              top: Math.min(drawDraft.startClient.y, drawDraft.currentClient.y) - (rfContainerRef.current?.getBoundingClientRect().top ?? 0),
              width: Math.max(24, Math.abs(drawDraft.currentClient.x - drawDraft.startClient.x)),
              height: Math.max(24, Math.abs(drawDraft.currentClient.y - drawDraft.startClient.y)),
              clipPath: drawDraft.type === "funnel" ? "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" : undefined,
            }}
          />
        )}
        {isDraggingOver && (
          <div className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-indigo-50/90 dark:bg-indigo-950/80 border-2 border-dashed border-indigo-400 dark:border-indigo-500 rounded-xl pointer-events-none">
            <UploadCloud size={40} className="text-indigo-500 dark:text-indigo-400" />
            <p className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
              Drop documents or .fmu files
            </p>
          </div>
        )}
        {simulateError && (
          <div
            className="absolute top-3 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-red-50 dark:bg-red-950 border border-red-300 dark:border-red-700 rounded-lg px-4 py-2 shadow-lg cursor-pointer"
            onClick={() => setSimulateError(null)}
          >
            <span className="text-xs text-red-700 dark:text-red-300">{simulateError}</span>
            <span className="text-xs text-red-400 ml-1">✕</span>
          </div>
        )}
        {rawNodes.length === 0 && documents.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none z-10">
            <div className="h-16 w-16 rounded-2xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center mb-4">
              <Network size={28} className="text-neutral-400 dark:text-neutral-500" />
            </div>
            <h3 className="text-base font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
              Canvas is empty
            </h3>
            <p className="text-sm text-neutral-400 dark:text-neutral-500 max-w-xs">
              Drag documents or FMUs from the library, or ask a technical question to build the graph.
            </p>
          </div>
        )}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeDragStart={onNodeDragStart}
          onNodeDrag={onNodeDrag}
          onNodeDragStop={onNodeDragStop}
          onNodesDelete={(deleted) => deleted.forEach((n) => {
            if (n.id.startsWith('__doc_')) onRemoveDocFromWorkspace?.(n.id.replace(/^__doc_/, ""));
            else onDeleteNode?.(n.id);
          })}
          onConnectStart={onConnectStart}
          onConnectEnd={onConnectEnd}
          onConnect={onConnect}
          onNodeDoubleClick={onNodeDoubleClick}
          onNodeContextMenu={onNodeContextMenu}
          onPaneClick={() => { setNewNodePopup(null); setContextMenu(null); }}
          onSelectionStart={onSelectionStart}
          onSelectionChange={onSelectionChange}
          selectionMode={SelectionMode.Partial}
          selectionOnDrag={!isInsertTool(activeTool) && activeTool !== "connect"}
          panOnDrag={[1]}
          autoPanOnNodeFocus={false}
          deleteKeyCode={["Delete", "Backspace"]}
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
          {contextMenu && (
            <NodeContextMenu
              {...contextMenu}
              onSetColor={(id, color) => { onSetNodeColor?.(id, color); setContextMenu(null); }}
              onDelete={contextMenu.nodeId.startsWith('__doc_')
                ? ((id) => onRemoveDocFromWorkspace?.(id.replace(/^__doc_/, "")))
                : onDeleteNode}
              onClose={() => setContextMenu(null)}
            />
          )}
        </ReactFlow>

        {/* Floating selection bar */}
        {selectedNodeIds.length >= 1 && onSaveSelection && (
          <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-xl shadow-lg px-4 py-2">
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {selectedNodeIds.length} node{selectedNodeIds.length > 1 ? 's' : ''} selected
            </span>
            <div className="w-px h-4 bg-neutral-200 dark:bg-neutral-700" />
            <button
              onClick={handleSaveSnippet}
              disabled={isSavingSnippet}
              className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-200 disabled:opacity-50 transition-colors"
            >
              {isSavingSnippet ? 'Saving…' : '⬆ Save to library'}
            </button>
          </div>
        )}
      </div>

      {pdfModal && (
        <PDFModal
          filename={pdfModal.filename}
          initialPage={pdfModal.page}
          highlights={pdfModal.highlights}
          onClose={() => setPdfModal(null)}
        />
      )}

      {newNodePopup && (
        <NewNodePicker
          screenX={newNodePopup.screenX}
          screenY={newNodePopup.screenY}
          onConfirm={handleNewNodeConfirm}
          onCancel={() => setNewNodePopup(null)}
        />
      )}
    </>
  );
}

export function CanvasGraph(props: CanvasGraphProps) {
  return (
    <ReactFlowProvider>
      <CanvasGraphInner {...props} />
    </ReactFlowProvider>
  );
}
