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
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  BackgroundVariant,
} from "@xyflow/react";
import { FloatingEdge } from "./FloatingEdge";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import { Network, UploadCloud, Layers, Box, MessageSquare, Palette } from "lucide-react";
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
  type CanvasNodeData,
  type ConceptNodeData,
  type DocumentNodeData,
  type FmuNodeData,
  type PlotNodeData,
} from "./KnowledgeNodes";
import { PDFModal, type PDFHighlight } from "./PDFModal";
import { useApp, type KBDocument } from "@/contexts/AppContext";
import { API_URL } from "@/lib/api-config";

// --- Types ---
interface Relation {
  from_id: string;
  to_id: string;
  label: string;
  document_id?: string;
  page?: number;
  bbox?: number[];
  highlights?: PDFHighlight[];
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

type CollapsibleNodeType = "concept" | "entity" | "category" | "topic";

// --- Node sizes (width × height in px) used by dagre for spacing ---
const NODE_SIZE: Record<string, { w: number; h: number }> = {
  conceptNode:  { w: 240, h: 60  },
  entityNode:   { w: 280, h: 70  },
  categoryNode: { w: 220, h: 55  },
  topicNode:    { w: 240, h: 60  },
  factNode:     { w: 280, h: 100 },
  sourceNode:   { w: 180, h: 40  },
  specNode:     { w: 260, h: 130 },
  fmuNode:      { w: 280, h: 200 },
  plotNode:     { w: 320, h: 220 },
  imageNode:    { w: 300, h: 200 },
};
const DEFAULT_SIZE = { w: 220, h: 80 };
const KNOWLEDGE_FILE_PATTERN = /\.(pdf|docx|txt|md|html)$/i;

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

function isCollapsibleNodeType(nodeType: CanvasNodeData["node_type"]): nodeType is CollapsibleNodeType {
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

function buildCollapsibleNodeData(
  node: CanvasNodeData,
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

// --- Add-node toolbar (bottom center) ---
type NewNodeType = 'concept' | 'entity' | 'fact';

function NodeAddToolbar({ onAddNode }: { onAddNode: (type: NewNodeType) => void }) {
  const ITEMS: { type: NewNodeType; label: string; icon: React.ReactNode; cls: string }[] = [
    { type: 'concept', label: 'Concept', icon: <Layers size={11} />,     cls: 'bg-violet-100 border-violet-400 text-violet-700 dark:bg-violet-950/40 dark:border-violet-600 dark:text-violet-300' },
    { type: 'entity',  label: 'Entity',  icon: <Box size={11} />,        cls: 'bg-slate-100 border-slate-400 text-slate-600 dark:bg-slate-900 dark:border-slate-600 dark:text-slate-300' },
    { type: 'fact',    label: 'Fact',    icon: <MessageSquare size={11} />, cls: 'bg-amber-100 border-amber-400 text-amber-700 dark:bg-amber-950/40 dark:border-amber-600 dark:text-amber-300' },
  ];
  return (
    <div className="absolute bottom-14 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 bg-white/90 dark:bg-neutral-900/90 backdrop-blur-sm border border-neutral-200 dark:border-neutral-700 rounded-xl px-2.5 py-1.5 shadow-md">
      <span className="text-[10px] text-neutral-400 font-medium pr-0.5">Add</span>
      {ITEMS.map(item => (
        <div
          key={item.type}
          draggable
          onDragStart={e => { e.dataTransfer.setData('application/anchor-nodetype', item.type); e.dataTransfer.effectAllowed = 'copy'; }}
          onClick={() => onAddNode(item.type)}
          className={`flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-lg border cursor-grab active:cursor-grabbing select-none transition-opacity hover:opacity-75 ${item.cls}`}
          title={`Drag to place or click to add ${item.label}`}
        >
          {item.icon}{item.label}
        </div>
      ))}
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
};

const edgeTypes: EdgeTypes = {
  floating: FloatingEdge,
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
  onFmuUploaded?: (payload: FmuUploadedPayload) => void;
  onSimulateComplete?: (fmuNodeId: string, jobId: string, filename: string, signalNames: string[], paramValues: Record<string, string>, stopTime: number) => void;
  onDeleteNode?: (nodeId: string) => void;
  onAddNode?: (node: any, relation: { from_id: string; to_id: string; label: string } | null) => void;
  onAddEdge?: (fromId: string, toId: string, label: string) => void;
  onSetNodeColor?: (nodeId: string, color: string) => void;
  workspaceDocIds?: string[];
  onAddDocToWorkspace?: (docId: string) => void;
  onFmuFromLibrary?: (filename: string) => void;
}

async function uploadCanvasFile(
  file: File,
  onFmuUploaded?: (payload: FmuUploadedPayload) => void,
) {
  if (file.name.endsWith(".fmu")) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_URL}/api/fmu/upload`, { method: "POST", body: formData });
    if (res.ok) {
      const data = await res.json();
      onFmuUploaded?.({ filename: data.filename, model_name: data.model_name, variables: data.variables ?? [] });
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

function CanvasGraphInner({ canvas, initialPositions = {}, onPositionsChange, onFmuUploaded, onSimulateComplete, onDeleteNode, onAddNode, onAddEdge, onSetNodeColor, workspaceDocIds, onAddDocToWorkspace, onFmuFromLibrary }: CanvasGraphProps) {
  const { screenToFlowPosition } = useReactFlow();
  const rfContainerRef = useRef<HTMLDivElement>(null);
  const { documents, refreshDocuments, activeDocumentId, setActiveDocumentId } = useApp();
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [pdfModal, setPdfModal] = useState<PDFModalState | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

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
    if (params.source && params.target) onAddEdge?.(params.source, params.target, '');
  }, [onAddEdge]);

  const onPaneDoubleClick = useCallback((event: React.MouseEvent) => {
    const target = event.target as Element;
    // Only trigger on the canvas pane background, not on nodes/handles/controls
    if (!target.closest('.react-flow__pane') || target.closest('.react-flow__node') || target.closest('.react-flow__controls')) return;
    const pos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setNewNodePopup({ screenX: event.clientX, screenY: event.clientY, flowX: pos.x, flowY: pos.y, sourceId: null });
  }, [screenToFlowPosition]);

  const _makeNode = useCallback((type: NewNodeType, label: string, flowPos: { x: number; y: number }) => {
    const id = `user_${type}_${Date.now()}`;
    const node: any = {
      id, node_type: type, status: 'found',
      title: type !== 'fact' ? label : '', text: type === 'fact' ? label : '',
      spec_title: '', properties: [], last_updated_run_id: '',
      filename: '', page: 0, bbox: [], highlights: [],
      fmu_filename: '', fmu_model_name: '', fmu_variables: [], fmu_param_values: {},
      plot_job_id: '', plot_fmu_filename: '', plot_signal_names: [], plot_stop_time: 10,
    };
    positionOverridesRef.current[id] = flowPos;
    return { id, node };
  }, []);

  const handleToolbarAdd = useCallback((type: NewNodeType) => {
    const rect = rfContainerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const jitter = () => (Math.random() - 0.5) * 80;
    const pos = screenToFlowPosition({ x: rect.left + rect.width / 2 + jitter(), y: rect.top + rect.height / 2 + jitter() });
    const label = type === 'fact' ? 'New fact' : `New ${type}`;
    const { node } = _makeNode(type, label, pos);
    onAddNode?.(node, null);
  }, [screenToFlowPosition, _makeNode, onAddNode]);

  const handleNewNodeConfirm = useCallback((type: NewNodeType, label: string) => {
    if (!newNodePopup) return;
    const { id, node } = _makeNode(type, label, { x: newNodePopup.flowX, y: newNodePopup.flowY });
    onAddNode?.(node, newNodePopup.sourceId ? { from_id: newNodePopup.sourceId, to_id: id, label: '' } : null);
    setNewNodePopup(null);
  }, [newNodePopup, _makeNode, onAddNode]);

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

  // Position overrides — manually dragged positions that survive layout re-runs
  const positionOverridesRef = useRef<Record<string, { x: number; y: number }>>(initialPositions);
  useEffect(() => {
    positionOverridesRef.current = { ...positionOverridesRef.current, ...initialPositions };
  }, [initialPositions]);

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
  }, []);

  const onNodeDrag = useCallback((_evt: React.MouseEvent, node: Node) => {
    const drag = dragStartRef.current;
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
  }, [setNodes]);

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
    const next = { ...positionOverridesRef.current, ...updates };
    positionOverridesRef.current = next;
    onPositionsChange?.(next);
  }, [onPositionsChange]);

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

  const rawNodes = canvas?.nodes ?? [];
  const relations = canvas?.relations ?? [];
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
  const buildDocNodes = useCallback((rels: Relation[]): Node[] => {
    const wsSet = workspaceDocIds && workspaceDocIds.length > 0 ? new Set(workspaceDocIds) : null;
    const uniqueDocs = Array.from(
      new Map(documentsRef.current
        .filter(d => wsSet === null || wsSet.has(d.document_id))
        .map(d => [d.document_id, d])
      ).values()
    );
    const activeId = activeDocumentIdRef.current;
    const onActivate = (id: string) => setActiveDocumentIdRef.current(id || null);
    return uniqueDocs.map((doc, i) => {
      const docNodeId = `__doc_${doc.document_id}`;
      const evidenceCount = rels.filter(r => r.to_id === docNodeId).length;
      return {
        id: docNodeId,
        type: "documentNode",
        position: { x: i * 176, y: -180 },
        draggable: true,
        data: {
          doc,
          isActive: doc.document_id === activeId,
          onActivate,
          onOpenPDF: handleOpenPDF,
          evidenceCount,
        } satisfies DocumentNodeData,
      };
    });
  }, [handleOpenPDF, workspaceDocIds]);

  useEffect(() => {
    const docNodes = buildDocNodes(relations);

    if (rawNodes.length === 0) {
      setNodes(docNodes);
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

    // Build RF nodes (no position yet — dagre will assign them)
    const rfNodes: Node[] = rawNodes.map((n) => {
      const hidden = hiddenIds.has(n.id);

      if (isCollapsibleNodeType(n.node_type)) {
        return buildFlowNode(
          n.id,
          COLLAPSIBLE_NODE_COMPONENTS[n.node_type],
          n.color,
          hidden,
          buildCollapsibleNodeData(n, childrenOf, collapsedIds, handleToggleCollapse, onDeleteNode),
        );
      }
      if (n.node_type === "fact") {
        return buildFlowNode(n.id, "factNode", n.color, hidden, {
          node: n,
          onOpenPDF: handleOpenPDF,
          onDelete: onDeleteNode,
          ...getEvidenceData(n.id, relations, documentsRef.current),
        });
      }
      if (n.node_type === "spec") {
        return buildFlowNode(n.id, "specNode", n.color, hidden, {
          node: n,
          onOpenPDF: handleOpenPDF,
          onDelete: onDeleteNode,
          ...getEvidenceData(n.id, relations, documentsRef.current),
        });
      }
      if (n.node_type === "image") {
        return buildFlowNode(n.id, "imageNode", n.color, hidden, {
          node: n,
          onOpenPDF: handleOpenPDF,
          onDelete: onDeleteNode,
        });
      }
      if (n.node_type === "fmu") {
        return buildFlowNode(n.id, "fmuNode", n.color, hidden, {
          node: n,
          onSimulate: handleSimulate,
          onDelete: onDeleteNode,
        } satisfies FmuNodeData);
      }
      if (n.node_type === "plot") {
        return buildFlowNode(n.id, "plotNode", n.color, hidden, {
          node: n,
          onDelete: onDeleteNode,
        } satisfies PlotNodeData);
      }
      // backward-compat: source/entity/category fallback
      return buildFlowNode(n.id, "sourceNode", n.color, hidden, {
        node: n,
        onOpenPDF: handleOpenPDF,
      });
    });

    const rfEdges: Edge[] = relations.map((r, idx) => {
      const fromNode = nodeMap.get(r.from_id);
      const toNode = nodeMap.get(r.to_id);
      const isConceptTopic = fromNode?.node_type === "concept";
      const isEntityCat = fromNode?.node_type === "entity";
      const isCatTopic  = fromNode?.node_type === "category";
      const isTopicFact = (fromNode?.node_type === "topic" || fromNode?.node_type === "category") && toNode?.node_type === "fact";
      const isSpec      = toNode?.node_type === "spec";
      const isEvidence  = r.to_id.startsWith('__doc_');
      const isSimPlot   = fromNode?.node_type === "fmu" && toNode?.node_type === "plot";
      const strokeColor = isSimPlot    ? "#14b8a6"
        : isConceptTopic ? "#8b5cf6"
        : isEntityCat ? "#64748b"
        : isCatTopic  ? "#3b82f6"
        : isTopicFact ? "#f59e0b"
        : isSpec       ? "#8b5cf6"
        : isEvidence   ? "#14b8a6"
        : "#6366f1";
      const docForEdge = isEvidence
        ? documentsRef.current.find(d => `__doc_${d.document_id}` === r.to_id)
        : undefined;
      return {
        id: `e-${idx}`,
        source: r.from_id,
        target: r.to_id,
        label: r.label || undefined,
        type: "floating",
        hidden: hiddenIds.has(r.from_id) || hiddenIds.has(r.to_id),
        animated: isConceptTopic || isEntityCat || isCatTopic,
        style: {
          stroke: strokeColor,
          strokeWidth: isEntityCat ? 2.5 : isConceptTopic || isCatTopic ? 2 : 1.5,
          strokeDasharray: isEvidence || isSpec ? "4 3" : undefined,
        },
        labelStyle: { fill: isSimPlot ? "#0f766e" : "#6366f1", fontWeight: 600, fontSize: 10 },
        labelBgStyle: { fill: isSimPlot ? "#f0fdfa" : "#f5f3ff", fillOpacity: 0.92 },
        labelBgPadding: [3, 2] as [number, number],
        data: isEvidence && r.page ? {
          page: r.page,
          bbox: r.bbox ?? [],
          highlights: r.highlights ?? [],
          document_id: r.document_id ?? '',
          filename: docForEdge?.filename ?? '',
          onOpenPDF: handleOpenPDF,
        } : undefined,
      };
    });

    // Build parent lookup (excluding evidence edges) for offset propagation
    const parentOf = new Map<string, string>();
    for (const r of relations) {
      if (!r.to_id.startsWith('__doc_')) parentOf.set(r.to_id, r.from_id);
    }

    const dagreResults = applyDagreLayout(rfNodes, rfEdges);
    const dagrePos = new Map(dagreResults.map((n) => [n.id, n.position]));

    const laidOut = dagreResults.map((n) => {
      const saved = positionOverridesRef.current[n.id];
      if (saved) return { ...n, position: saved };

      // New node — walk up to find the closest ancestor with a saved position
      // and apply the same offset so it lands near its actual parent.
      let cur = n.id;
      while (parentOf.has(cur)) {
        const par = parentOf.get(cur)!;
        const parSaved = positionOverridesRef.current[par];
        const parDagre = dagrePos.get(par);
        if (parSaved && parDagre) {
          const dx = parSaved.x - parDagre.x;
          const dy = parSaved.y - parDagre.y;
          const base = dagrePos.get(n.id)!;
          return { ...n, position: { x: base.x + dx, y: base.y + dy } };
        }
        cur = par;
      }
      return n;
    });
    const docNodesWithOverrides = docNodes.map((n) => {
      const saved = positionOverridesRef.current[n.id];
      return saved ? { ...n, position: saved } : n;
    });
    setNodes([...docNodesWithOverrides, ...laidOut]);
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

    setNodes((prev) =>
      prev.map((rfNode) => {
        const n = nodeMap.get(rfNode.id);
        if (!n) return rfNode;
        if (isCollapsibleNodeType(n.node_type)) {
          return {
            ...rfNode,
            data: {
              ...rfNode.data,
              ...buildCollapsibleNodeData(n, childrenOf, collapsedIds, handleToggleCollapse, onDeleteNode),
            },
          };
        }
        if (n.node_type === "fact" || n.node_type === "spec") {
          return {
            ...rfNode,
            data: {
              ...rfNode.data,
              node: n,
              onOpenPDF: handleOpenPDF,
              onDelete: onDeleteNode,
              ...getEvidenceData(n.id, relations, documentsRef.current),
            },
          };
        }
        if (n.node_type === "fmu") {
          return { ...rfNode, data: { ...rfNode.data, node: n, onSimulate: handleSimulate } };
        }
        if (n.node_type === "plot") {
          return { ...rfNode, data: { ...rfNode.data, node: n } };
        }
        if (n.node_type === "image") {
          return { ...rfNode, data: { ...rfNode.data, node: n, onOpenPDF: handleOpenPDF, onDelete: onDeleteNode } };
        }
        return { ...rfNode, data: { ...rfNode.data, node: n } };
      })
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawNodes, relations]);

  // File drop handlers
  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    const t = e.dataTransfer.types;
    const hasFiles = t.includes("Files");
    const hasLibItem = t.includes("application/anchor-doc") || t.includes("application/anchor-fmu");
    const hasNodeType = t.includes("application/anchor-nodetype");
    if (!hasFiles && !hasLibItem && !hasNodeType) return;
    e.preventDefault();
    setIsDraggingOver(hasFiles || hasLibItem);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Element | null)) {
      setIsDraggingOver(false);
    }
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingOver(false);

    // Handle toolbar node-type drops
    const nodeType = e.dataTransfer.getData("application/anchor-nodetype") as NewNodeType | '';
    if (nodeType) {
      const pos = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      const label = nodeType === 'fact' ? 'New fact' : `New ${nodeType}`;
      const { node } = _makeNode(nodeType, label, pos);
      onAddNode?.(node, null);
      return;
    }

    // Handle library drawer drops (doc or fmu already on server)
    const docId = e.dataTransfer.getData("application/anchor-doc");
    const fmuFilename = e.dataTransfer.getData("application/anchor-fmu");
    if (docId) { onAddDocToWorkspace?.(docId); return; }
    if (fmuFilename) { onFmuFromLibrary?.(fmuFilename); return; }

    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;
    try {
      await Promise.all(files.map((file) => uploadCanvasFile(file, onFmuUploaded)));
      refreshDocuments();
    } catch {
      // upload failed — user can retry; suppress to avoid dev overlay noise
    }
  }, [onAddDocToWorkspace, onAddNode, onFmuFromLibrary, onFmuUploaded, refreshDocuments, screenToFlowPosition, _makeNode]);

  return (
    <>
      <div
        ref={rfContainerRef}
        className="w-full h-full overflow-hidden relative"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onDoubleClick={onPaneDoubleClick}
      >
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
          onNodesDelete={(deleted) => deleted.forEach((n) => { if (!n.id.startsWith('__doc_')) onDeleteNode?.(n.id); })}
          onConnectStart={onConnectStart}
          onConnectEnd={onConnectEnd}
          onConnect={onConnect}
          onNodeContextMenu={onNodeContextMenu}
          onPaneClick={() => { setNewNodePopup(null); setContextMenu(null); }}
          deleteKeyCode={["Delete", "Backspace"]}
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
          {contextMenu && (
            <NodeContextMenu
              {...contextMenu}
              onSetColor={(id, color) => { onSetNodeColor?.(id, color); setContextMenu(null); }}
              onDelete={!contextMenu.nodeId.startsWith('__doc_') ? onDeleteNode : undefined}
              onClose={() => setContextMenu(null)}
            />
          )}
        </ReactFlow>
        <NodeAddToolbar onAddNode={handleToolbarAdd} />
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
