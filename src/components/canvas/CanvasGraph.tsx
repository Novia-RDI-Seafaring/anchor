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
import { Network, UploadCloud, Layers, Box, MessageSquare, MousePointer2, Hand, Filter, SquareDashed, Wand2, Square, Circle, Diamond, ArrowRight, Type, Trash2, Cpu, StickyNote, FileText, Activity } from "lucide-react";
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
  ModelNode,
  type CanvasNodeData,
  type ConceptNodeData,
  type DocumentNodeData,
  type FmuNodeData,
  type PlotNodeData,
  type FunnelNodeData,
  type AreaNodeData,
  type ModelNodeData,
  SquareShapeNode,
  CircleShapeNode,
  DiamondShapeNode,
  NoteNode,
  RichTextNode,
  type SquareShapeNodeData,
  type CircleShapeNodeData,
  type DiamondShapeNodeData,
  type NoteNodeData,
  type RichTextNodeData,
} from "./KnowledgeNodes";
import {
  adaptDocumentToCanvasItem,
  adaptLegacyNodeToCanvasItem,
  type CanvasItem,
  type LegacyCanvasNode,
} from "./canvas-model";
import {
  anchorAtCenter,
  buildDerivedEvidenceRelations,
  buildSourceColorMap,
  computeNodeSources,
  DEFAULT_SIZE,
  DOCUMENT_NODE_SIZE,
  findBestAreaParent,
  inferNodeSize,
  KNOWLEDGE_FILE_PATTERN,
  NODE_SIZE,
  pickEdgeSourceColor,
  type Relation,
} from "./canvasGraphUtils";
import {
  applyExplicitNodeSize,
  applyMindmapLayout,
  buildCollapsibleNodeData,
  buildFlowNode,
  COLLAPSIBLE_NODE_COMPONENTS,
  connectedComponents,
  descendants,
  getEvidenceData,
  isCollapsibleNodeType,
  nodeStyle,
  placeNodesManually,
  type CollapsibleNodeType,
  type FlowPosition,
} from "./canvasGraphLayoutUtils";
import { PDFModal, type PDFHighlight } from "./PDFModal";
import { ResourcePalette, type PaletteTab } from "./ResourcePalette";
import { useApp, type KBDocument } from "@/contexts/AppContext";
import { API_URL } from "@/lib/api-config";

// --- Types ---
interface CanvasState {
  nodes: LegacyCanvasNode[];
  relations: Relation[];
}

interface PDFModalState {
  filename: string;
  page: number;
  highlights: PDFHighlight[];
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

type NewNodeType = 'concept' | 'entity' | 'fact' | 'funnel' | 'area' | 'model' | 'square' | 'circle_shape' | 'diamond_shape' | 'note' | 'rich_text';
type CanvasTool = "move" | "select" | "connect" | NewNodeType;

const INSERT_TOOLS = new Set<string>(['concept', 'entity', 'fact', 'funnel', 'area', 'model', 'square', 'circle_shape', 'diamond_shape', 'note', 'rich_text']);
function isInsertTool(tool: CanvasTool): tool is NewNodeType {
  return INSERT_TOOLS.has(tool);
}

function LeftToolRail({
  activeTool,
  onChange,
  onArrange,
  openPalette,
  onTogglePalette,
}: {
  activeTool: CanvasTool;
  onChange: (t: CanvasTool) => void;
  onArrange?: () => void;
  openPalette: PaletteTab | null;
  onTogglePalette: (tab: PaletteTab, anchorY: number) => void;
}) {
  const insertTools: Array<{ id: CanvasTool; icon: React.ReactNode; label: string; shortcut?: string }> = [
    { id: "model",         icon: <Cpu size={15} />,          label: "Model",   shortcut: "1" },
  ];

  const resourceButtons: Array<{ tab: PaletteTab; icon: React.ReactNode; label: string }> = [
    { tab: "docs",     icon: <FileText size={15} />, label: "Documents" },
    { tab: "fmus",     icon: <Activity size={15} />,  label: "FMU Models" },
    { tab: "snippets", icon: <Network size={15} />,   label: "Snippets" },
  ];

  const btnRef = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
      if (e.key === "v" || e.key === "V") onChange("select");
      if (e.key === "1") onChange("model");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onChange]);

  const toolBtnClass = (active: boolean) =>
    `flex h-10 w-10 items-center justify-center rounded-2xl border transition-colors ${
      active
        ? "border-indigo-300 bg-indigo-100 text-indigo-700 dark:border-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-300"
        : "border-transparent text-neutral-500 hover:border-neutral-200 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:border-neutral-700 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
    }`;

  return (
    <div className="absolute left-4 top-20 z-30 flex flex-col gap-2 rounded-[22px] border border-neutral-200/80 bg-white/94 p-2 shadow-[0_14px_40px_rgba(15,23,42,0.10)] backdrop-blur-md dark:border-neutral-700/80 dark:bg-neutral-900/94">
      {/* Insert tools */}
      <div className="flex flex-col gap-1.5">
        {insertTools.map((tool) => (
          <button
            key={tool.id}
            onClick={() => onChange(tool.id)}
            title={tool.shortcut ? `${tool.label} (${tool.shortcut})` : tool.label}
            className={toolBtnClass(activeTool === tool.id)}
          >
            {tool.icon}
          </button>
        ))}
      </div>
      <div className="mx-auto h-px w-8 bg-neutral-200 dark:bg-neutral-700" />
      {/* Resource palettes */}
      <div className="flex flex-col gap-1.5">
        {resourceButtons.map((rb) => (
          <button
            key={rb.tab}
            ref={(el) => { btnRef.current[rb.tab] = el; }}
            onClick={() => {
              const rect = btnRef.current[rb.tab]?.getBoundingClientRect();
              onTogglePalette(rb.tab, rect ? rect.top : 120);
            }}
            title={rb.label}
            className={toolBtnClass(openPalette === rb.tab)}
          >
            {rb.icon}
          </button>
        ))}
      </div>
      <div className="mx-auto h-px w-8 bg-neutral-200 dark:bg-neutral-700" />
      {/* Utilities */}
      <div className="flex flex-col gap-1.5">
        <button
          onClick={onArrange}
          title="Arrange canvas"
          className={toolBtnClass(false)}
        >
          <Wand2 size={15} />
        </button>
      </div>
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
  modelNode:    ModelNode,
  areaNode:     AreaNode,
  squareShapeNode:  SquareShapeNode,
  circleShapeNode:  CircleShapeNode,
  diamondShapeNode: DiamondShapeNode,
  noteNode:         NoteNode,
  richTextNode:     RichTextNode,
};

const edgeTypes: EdgeTypes = {
  floating: FloatingEdge,
  anchored: AnchoredEdge,
};


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
  showInternalToolbar?: boolean;
  onFmuUploaded?: (payload: FmuUploadedPayload, position?: FlowPosition) => void;
  onSimulateComplete?: (fmuNodeId: string, jobId: string, filename: string, signalNames: string[], paramValues: Record<string, string>, stopTime: number) => void;
  onDeleteNode?: (nodeId: string) => void;
  onAddNode?: (node: any, relation: { from_id: string; to_id: string; label: string } | null) => void;
  onAddEdge?: (fromId: string, toId: string, label: string, sourceHandle?: string | null, targetHandle?: string | null) => void;
  onDeleteEdge?: (fromId: string, toId: string, sourceHandle?: string, targetHandle?: string) => void;
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
  onUpdateNode?: (nodeId: string, updates: Record<string, unknown>) => void;
  onSaveSelection?: (selectedNodeIds: string[], name?: string) => Promise<void>;
  onParameterLookup?: (documentFilename: string, modelNodeId: string, params: Array<{ fmuNodeId: string; paramName: string; unit?: string }>) => void;
}

function compactText(value: string, limit = 220): string {
  const flattened = value.replace(/[#*_`>-]/g, " ").replace(/\s+/g, " ").trim();
  if (!flattened) return "";
  return flattened.length > limit ? `${flattened.slice(0, limit - 1)}…` : flattened;
}

function summarizeNodeForChat(node: CanvasItem): string {
  if (node.semanticType === "fact") {
    return compactText(node.text || "");
  }
  if (node.semanticType === "spec") {
    const sections = node.parameter_sections ?? [];
    if (sections.length > 0) {
      return sections
        .flatMap((section) => section.rows.slice(0, 2).map((row) => `${section.name}: ${row.parameter} = ${row.value}${row.unit ? ` ${row.unit}` : ""}`))
        .slice(0, 3)
        .join("; ");
    }
    const props = node.properties ?? [];
    return props
      .slice(0, 3)
      .map((property) => `${property.key}: ${property.value}`)
      .join("; ");
  }
  if (node.semanticType === "image") {
    return compactText(node.image_caption || node.text || node.title || "Selected visual region");
  }
  return compactText(node.text || node.title || "");
}

async function uploadCanvasFile(
  file: File,
  onFmuUploaded?: (payload: FmuUploadedPayload, position?: FlowPosition) => void,
  position?: FlowPosition,
): Promise<string | null> {
  if (file.name.endsWith(".fmu")) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_URL}/api/fmu/upload`, { method: "POST", body: formData });
    if (res.ok) {
      const data = await res.json();
      onFmuUploaded?.({ filename: data.filename, model_name: data.model_name, variables: data.variables ?? [] }, position);
    }
    return null;
  }

  if (!KNOWLEDGE_FILE_PATTERN.test(file.name)) {
    return null;
  }

  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_URL}/api/documents/upload`, { method: "POST", body: formData });
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.statusText}`);
  }
  const data = await res.json();
  return data?.document?.document_id ?? null;
}

function CanvasGraphInner({ canvas, initialPositions = {}, onPositionsChange, showInternalToolbar = true, onFmuUploaded, onSimulateComplete, onDeleteNode, onAddNode, onAddEdge, onDeleteEdge, onSetNodeColor, workspaceDocIds, onAddDocToWorkspace, onRemoveDocFromWorkspace, onSetParent, onFmuFromLibrary, onAddSnippet, onUpdateNode, onSaveSelection, onParameterLookup }: CanvasGraphProps) {
  const { screenToFlowPosition } = useReactFlow();
  const rfContainerRef = useRef<HTMLDivElement>(null);
  const connectStartRef = useRef<{ nodeId: string; handleId: string; handleType: 'source' | 'target' } | null>(null);
  const { documents, refreshDocuments, activeDocumentId, setActiveDocumentId, addFocusedChatNode } = useApp();
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [pdfModal, setPdfModal] = useState<PDFModalState | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [highlightedAreaId, setHighlightedAreaId] = useState<string | null>(null);
  const [previewedSource, setPreviewedSource] = useState<{ filename: string; page: number } | null>(null);

  // Resource palette state (replaces sidebar drawer)
  const [openPalette, setOpenPalette] = useState<PaletteTab | null>(null);
  const [paletteAnchorY, setPaletteAnchorY] = useState(120);

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

  const focusNodeForChat = useCallback((node: CanvasItem, evidence?: { filename?: string; page?: number; bbox?: number[] }) => {
    addFocusedChatNode({
      nodeId: node.id,
      nodeType: node.semanticType,
      title: node.title || node.spec_title || node.image_caption || "Canvas node",
      summary: summarizeNodeForChat(node),
      filename: evidence?.filename || node.image_filename || node.filename || "",
      page: evidence?.page || node.image_page || node.page || 0,
      bbox: evidence?.bbox || node.image_bbox || node.bbox || [],
    });
  }, [addFocusedChatNode]);


  // --- Drag-from-handle: create model node on empty canvas, auto-connect ---

  const onConnectStart = useCallback(
    (_event: any, params: { nodeId: string | null; handleId: string | null; handleType: 'source' | 'target' | null }) => {
      console.log('[onConnectStart]', params);
      if (params.nodeId && params.handleId && params.handleType) {
        connectStartRef.current = {
          nodeId: params.nodeId,
          handleId: params.handleId,
          handleType: params.handleType,
        };
      }
    },
    [],
  );

  const triggerLookupRef = useRef<((s: string, t: string) => void) | null>(null);

  const onConnect = useCallback((params: any) => {
    if (params.source && params.target) {
      onAddEdge?.(params.source, params.target, '', params.sourceHandle ?? null, params.targetHandle ?? null);
      // Check if this model↔document connection should trigger param lookup
      triggerLookupRef.current?.(params.source, params.target);
    }
  }, [onAddEdge]);

  const handleCanvasMouseDown = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!isInsertTool(activeTool) || event.button !== 0) return;
    const target = event.target as Element;
    if (!target.closest('.react-flow__pane')) return;
    event.preventDefault();
    event.stopPropagation();
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setSelectedNodeIds([]);
    setDrawDraft({
      type: activeTool,
      startClient: { x: event.clientX, y: event.clientY },
      currentClient: { x: event.clientX, y: event.clientY },
      startFlow: flowPos,
      currentFlow: flowPos,
    });
  }, [activeTool, screenToFlowPosition]);


  const nodeSizeKey = useCallback((type: NewNodeType): string => {
    const map: Record<string, string> = {
      square: 'squareShapeNode', circle_shape: 'circleShapeNode', diamond_shape: 'diamondShapeNode',
      note: 'noteNode', rich_text: 'richTextNode',
      funnel: 'funnelNode', area: 'areaNode', fact: 'factNode',
      entity: 'entityNode', model: 'modelNode', concept: 'conceptNode',
    };
    return map[type] ?? 'conceptNode';
  }, []);

  const _makeNode = useCallback((type: NewNodeType, label: string, flowPos: { x: number; y: number }) => {
    const id = `user_${type}_${Date.now()}`;
    const sizeKey = nodeSizeKey(type);
    const isShape = type === 'square' || type === 'circle_shape' || type === 'diamond_shape';
    const isNote = type === 'note';
    const isRichText = type === 'rich_text';
    const node: any = {
      id, node_type: type, status: 'found',
      title: isShape ? '' : isNote || isRichText ? '' : (type !== 'fact' && type !== 'funnel' && type !== 'area' && type !== 'model') ? label : '',
      text: isNote ? '' : isRichText ? '' : type === 'fact' ? label : '',
      spec_title: '', properties: [], last_updated_run_id: '',
      filename: '', page: 0, bbox: [], highlights: [],
      fmu_filename: '', fmu_model_name: '', fmu_variables: [], fmu_param_values: {},
      plot_job_id: '', plot_fmu_filename: '', plot_signal_names: [], plot_stop_time: 10,
      funnel_label: type === 'funnel' ? (label || 'Funnel') : '',
      area_label: type === 'area' ? (label || 'Area') : '',
      area_width: type === 'area' ? 600 : 0,
      area_height: type === 'area' ? 400 : 0,
      model_label: type === 'model' ? (label || 'Model') : '',
      width: NODE_SIZE[sizeKey]?.w ?? 220,
      height: NODE_SIZE[sizeKey]?.h ?? 80,
      parent_id: '',
    };
    positionOverridesRef.current[id] = flowPos;
    return { id, node };
  }, [nodeSizeKey]);

  const createToolbarNode = useCallback((type: NewNodeType, startFlow: FlowPosition, currentFlow: FlowPosition) => {
    const draftLeft = Math.min(startFlow.x, currentFlow.x);
    const draftTop = Math.min(startFlow.y, currentFlow.y);
    const draftWidth = Math.abs(currentFlow.x - startFlow.x);
    const draftHeight = Math.abs(currentFlow.y - startFlow.y);
    const nodeSize = NODE_SIZE[nodeSizeKey(type)] ?? DEFAULT_SIZE;
    const center = {
      x: draftLeft + Math.max(draftWidth, nodeSize.w) / 2,
      y: draftTop + Math.max(draftHeight, nodeSize.h) / 2,
    };
    const basePosition = type === "area"
      ? { x: draftLeft, y: draftTop }
      : anchorAtCenter(center, nodeSize);
    const label = type === 'square' || type === 'circle_shape' || type === 'diamond_shape' || type === 'note' || type === 'rich_text'
      ? ''
      : type === 'model' ? 'Model' : type === 'fact' ? 'New note' : `New ${type}`;
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

  // Drag from FMU handle to empty canvas → create model node at drop position
  const onConnectEnd = useCallback(
    (event: MouseEvent | TouchEvent) => {
      const start = connectStartRef.current;
      connectStartRef.current = null;
      if (!start) return;

      // Only act when the drag originated from an FMU-style handle
      const isFmuHandle =
        start.handleId.startsWith('in-') ||
        start.handleId.startsWith('out-') ||
        start.handleId.startsWith('param-in-');
      if (!isFmuHandle) return;

      // Check if dropped on empty canvas (not on a handle or node)
      const target = event.target as Element;
      console.log('[onConnectEnd] target:', target.className, 'start:', start);
      const droppedOnHandle = target.closest('.react-flow__handle');
      const droppedOnNode = target.closest('.react-flow__node');
      if (droppedOnHandle || droppedOnNode) return;

      // Get drop position in flow coordinates
      const clientX = 'changedTouches' in event
        ? (event as TouchEvent).changedTouches[0]?.clientX ?? 0
        : (event as MouseEvent).clientX;
      const clientY = 'changedTouches' in event
        ? (event as TouchEvent).changedTouches[0]?.clientY ?? 0
        : (event as MouseEvent).clientY;
      const flowPos = screenToFlowPosition({ x: clientX, y: clientY });

      // Extract variable name from handle ID for auto-label
      let autoLabel = '';
      if (start.handleId.startsWith('param-in-')) {
        autoLabel = start.handleId.replace('param-in-', '');
      } else if (start.handleId.startsWith('in-')) {
        autoLabel = start.handleId.replace('in-', '');
      } else if (start.handleId.startsWith('out-')) {
        autoLabel = start.handleId.replace('out-', '');
      }

      // Create a model node at the drop position
      const { id: modelId, node: modelNode } = _makeNode('model', autoLabel, flowPos);
      commitPositionOverrides({ [modelId]: flowPos }, true);
      onAddNode?.(modelNode, null);

      // Create edge with correct direction based on FMU handle type
      if (start.handleType === 'target') {
        // FMU handle is a target (input/param) — model feeds INTO the FMU
        onAddEdge?.(modelId, start.nodeId, '', 'right', start.handleId);
      } else {
        // FMU handle is a source (output) — FMU feeds INTO the model
        onAddEdge?.(start.nodeId, modelId, '', start.handleId, 'left');
      }
    },
    [screenToFlowPosition, _makeNode, commitPositionOverrides, onAddNode, onAddEdge],
  );

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

  // Trigger parameter lookup when a model↔document edge is created
  const triggerParameterLookupIfNeeded = useCallback((
    sourceId: string,
    targetId: string,
  ) => {
    const allCanvasNodes = (canvas as any)?.nodes ?? [];
    const allRelations: Relation[] = (canvas as any)?.relations ?? [];

    let modelNodeId: string | undefined;
    let docNodeId: string | undefined;

    const sourceIsDoc = sourceId.startsWith('__doc_');
    const targetIsDoc = targetId.startsWith('__doc_');
    const sourceRaw = allCanvasNodes.find((n: any) => n.id === sourceId);
    const targetRaw = allCanvasNodes.find((n: any) => n.id === targetId);

    if (sourceRaw?.node_type === 'model' && targetIsDoc) {
      modelNodeId = sourceId;
      docNodeId = targetId;
    } else if (targetRaw?.node_type === 'model' && sourceIsDoc) {
      modelNodeId = targetId;
      docNodeId = sourceId;
    } else {
      return;
    }

    const docId = docNodeId.replace(/^__doc_/, '');
    const doc = documentsRef.current.find(d => d.document_id === docId);
    if (!doc?.filename) return;

    // Find FMU param handles connected to this model node
    const connectedFmuParams: Array<{ fmuNodeId: string; paramName: string; unit?: string }> = [];
    for (const r of allRelations) {
      if (r.from_id === modelNodeId && (r.target_handle?.startsWith('param-in-') || r.target_handle?.startsWith('in-'))) {
        const paramName = r.target_handle!.startsWith('param-in-')
          ? r.target_handle!.replace('param-in-', '')
          : r.target_handle!.replace('in-', '');
        const fmuNode = allCanvasNodes.find((n: any) => n.id === r.to_id);
        const fmuVar = (fmuNode?.fmu_variables ?? []).find((v: any) => v.name === paramName);
        connectedFmuParams.push({ fmuNodeId: r.to_id, paramName, unit: fmuVar?.unit });
      }
    }

    if (connectedFmuParams.length === 0) return;
    onParameterLookup?.(doc.filename, modelNodeId, connectedFmuParams);
  }, [canvas, onParameterLookup]);

  // Keep ref in sync so onConnect can call the trigger without a dep cycle
  useEffect(() => { triggerLookupRef.current = triggerParameterLookupIfNeeded; }, [triggerParameterLookupIfNeeded]);

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
          buildCollapsibleNodeData(n, childrenOf, collapsedIds, handleToggleCollapse, onDeleteNode, onSetNodeColor),
        ), n.semanticType === "entity" ? NODE_SIZE.entityNode! : n.semanticType === "topic" ? NODE_SIZE.topicNode! : n.semanticType === "category" ? NODE_SIZE.categoryNode! : NODE_SIZE.conceptNode!);
      }
      if (n.semanticType === "fact") {
        const evidence = getEvidenceData(n.id, relations, documentsRef.current);
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "factNode", n.color, hidden, {
          node: n,
          onOpenPDF: handleOpenPDF,
          onUseInChat: () => focusNodeForChat(n, {
            filename: evidence.evidenceFilename,
            page: evidence.evidencePage,
            bbox: evidence.evidenceHighlights?.[0]?.bbox ?? [],
          }),
          onPreviewSource: (filename: string | null, page?: number | null) => setPreviewedSource(filename && page ? { filename, page } : null),
          onDelete: onDeleteNode,
          onSetColor: onSetNodeColor,
          onUpdateText: (nodeId: string, text: string) => onUpdateNode?.(nodeId, { text, title: "Explanation" }),
          ...evidence,
        }), NODE_SIZE.factNode!);
      }
      if (n.semanticType === "spec") {
        const evidence = getEvidenceData(n.id, relations, documentsRef.current);
        const specFlowNode = buildFlowNode(n.id, "specNode", n.color, hidden, {
          node: n,
          onOpenPDF: handleOpenPDF,
          onUseInChat: () => focusNodeForChat(n, {
            filename: evidence.evidenceFilename,
            page: evidence.evidencePage,
            bbox: evidence.evidenceHighlights?.[0]?.bbox ?? [],
          }),
          onPreviewSource: (filename: string | null, page?: number | null) => setPreviewedSource(filename && page ? { filename, page } : null),
          onDelete: onDeleteNode,
          onSetColor: onSetNodeColor,
          ...evidence,
        });
        // Let spec nodes auto-size to fit content (handles + source buttons)
        return { ...specFlowNode, width: undefined, height: undefined, style: { ...specFlowNode.style, width: "auto", height: "auto" } };
      }
      if (n.semanticType === "document") {
        const doc = documentsRef.current.find((item) => item.document_id === n.id.replace(/^__doc_/, ""));
        const evidenceCount = relations.filter(r => r.to_id === n.id).length;
        const readableDocNode = {
          ...n,
          width: Math.max(n.width || 0, DOCUMENT_NODE_SIZE.w),
          height: Math.max(n.height || 0, DOCUMENT_NODE_SIZE.h),
        };
        return applyExplicitNodeSize(readableDocNode, buildFlowNode(n.id, "documentNode", n.color, hidden, {
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
          onUseInChat: () => focusNodeForChat(n),
          onDelete: onDeleteNode,
          onSetColor: onSetNodeColor,
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
      if (n.semanticType === "model") {
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "modelNode", n.color, hidden, {
          node: n,
          onDelete: onDeleteNode,
          onSetColor: onSetNodeColor,
          onUpdateLabel: (nodeId: string, label: string) => onUpdateNode?.(nodeId, { model_label: label, title: label }),
        } satisfies ModelNodeData), NODE_SIZE.modelNode!);
      }
      if (n.semanticType === "funnel") {
        const connectedDocCount = relations.filter(r => r.to_id === n.id && r.from_id.startsWith('__doc_')).length;
        return applyExplicitNodeSize(n, buildFlowNode(n.id, "funnelNode", n.color, hidden, {
          node: n,
          onDelete: onDeleteNode,
          onSetColor: onSetNodeColor,
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
          onSetColor: onSetNodeColor,
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
      // New shape/note/text nodes
      const shapeNodeMap: Record<string, { rfType: string; size: { w: number; h: number } }> = {
        square:        { rfType: "squareShapeNode",  size: NODE_SIZE.squareShapeNode! },
        circle_shape:  { rfType: "circleShapeNode",  size: NODE_SIZE.circleShapeNode! },
        diamond_shape: { rfType: "diamondShapeNode", size: NODE_SIZE.diamondShapeNode! },
        note:          { rfType: "noteNode",         size: NODE_SIZE.noteNode! },
        rich_text:     { rfType: "richTextNode",     size: NODE_SIZE.richTextNode! },
      };
      const shapeInfo = shapeNodeMap[n.semanticType];
      if (shapeInfo) {
        return applyExplicitNodeSize(n, buildFlowNode(n.id, shapeInfo.rfType, n.color, hidden, {
          node: n,
          onDelete: onDeleteNode,
          onSetColor: onSetNodeColor,
          onUpdateText: (nodeId: string, text: string) => onUpdateNode?.(nodeId, { text, title: text }),
        }), shapeInfo.size);
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
        animated: true,
        style: {
          stroke: strokeColor,
          strokeWidth: isEntityCat ? 3.5 : isConceptTopic || isCatTopic ? 3 : isTopicFact || isSpec ? 2.5 : isEvidence ? 1.8 : 2,
          strokeDasharray: "5 4",
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
              ...buildCollapsibleNodeData(n, childrenOf, collapsedIds, handleToggleCollapse, onDeleteNode, onSetNodeColor),
            },
          };
        }
        if (n.semanticType === "fact" || n.semanticType === "spec") {
          const evidence = getEvidenceData(n.id, relations, documentsRef.current);
          return {
            ...rfNode,
            data: {
              ...rfNode.data,
              node: n,
              onOpenPDF: handleOpenPDF,
              onUseInChat: () => focusNodeForChat(n, {
                filename: evidence.evidenceFilename,
                page: evidence.evidencePage,
                bbox: evidence.evidenceHighlights?.[0]?.bbox ?? [],
              }),
              onPreviewSource: (filename: string | null, page?: number | null) => setPreviewedSource(filename && page ? { filename, page } : null),
              onDelete: onDeleteNode,
              onSetColor: onSetNodeColor,
              onUpdateText: n.semanticType === "fact" ? (nodeId: string, text: string) => onUpdateNode?.(nodeId, { text, title: "Explanation" }) : undefined,
              ...evidence,
            },
          };
        }
        if (n.semanticType === "document") {
          const doc = documentsRef.current.find((item) => item.document_id === n.id.replace(/^__doc_/, ""));
          const width = Math.max(n.width || 0, DOCUMENT_NODE_SIZE.w);
          const height = Math.max(n.height || 0, DOCUMENT_NODE_SIZE.h);
          return {
            ...rfNode,
            style: {
              ...rfNode.style,
              width,
              height,
            },
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
          return { ...rfNode, data: { ...rfNode.data, node: n, onOpenPDF: handleOpenPDF, onUseInChat: () => focusNodeForChat(n), onDelete: onDeleteNode, onSetColor: onSetNodeColor } };
        }
        return { ...rfNode, data: { ...rfNode.data, node: n, onSetColor: onSetNodeColor, onDelete: onDeleteNode, onUpdateText: (nodeId: string, text: string) => onUpdateNode?.(nodeId, { text, title: text }) } };
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
    const hasRegion = t.includes("application/anchor-region");
    const hasChatMessage = t.includes("application/anchor-chat-message");
    if (!hasFiles && !hasLibItem && !hasNodeType && !hasRegion && !hasChatMessage) return;
    e.preventDefault();
    setIsDraggingOver(hasFiles || hasLibItem || hasChatMessage);
    const absolutePosition = screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const nodeType = e.dataTransfer.getData("application/anchor-nodetype") as NewNodeType | '';
    const fmuFilename = e.dataTransfer.getData("application/anchor-fmu");
    const docId = e.dataTransfer.getData("application/anchor-doc");
    const snippetPayload = e.dataTransfer.getData("application/anchor-snippet");
    const size =
      nodeType === "area" ? null
      : nodeType ? (NODE_SIZE[nodeSizeKey(nodeType)] ?? null)
      : fmuFilename ? NODE_SIZE.fmuNode
      : docId ? DOCUMENT_NODE_SIZE
      : snippetPayload ? { w: 220, h: 84 }
      : hasRegion ? NODE_SIZE.imageNode
      : hasChatMessage ? { w: 340, h: 180 }
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
      const nodeSize = NODE_SIZE[nodeSizeKey(nodeType)] ?? DEFAULT_SIZE;
      const absolutePos = anchorAtCenter(
        screenToFlowPosition({ x: e.clientX, y: e.clientY }),
        nodeSize,
      );
      const areaParent = nodeType === "area"
        ? null
        : findBestAreaParent(absolutePos, nodeSize, nodesRef.current);
      const pos = areaParent?.position ?? absolutePos;
      const label = nodeType === 'square' || nodeType === 'circle_shape' || nodeType === 'diamond_shape' || nodeType === 'note' || nodeType === 'rich_text'
        ? ''
        : nodeType === 'fact' ? 'New fact' : nodeType === 'model' ? 'Model' : `New ${nodeType}`;
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
    const chatMessagePayload = e.dataTransfer.getData("application/anchor-chat-message");
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
            : rawNode?.node_type === "model" ? NODE_SIZE.modelNode!
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
    if (chatMessagePayload) {
      try {
        const parsed = JSON.parse(chatMessagePayload);
        const content = String(parsed?.content ?? "").trim();
        if (!content) return;
        const source = parsed?.source && typeof parsed.source === "object" ? parsed.source : {};
        const sourceFilename = typeof source.filename === "string" ? source.filename : "";
        const sourcePage = Number(source.page ?? 0);
        const sourceBbox = Array.isArray(source.bbox) && source.bbox.length === 4
          ? source.bbox.map((item: any) => Number(item)).filter((item: number) => Number.isFinite(item))
          : [];
        const sourceHighlights = Array.isArray(source.highlights) ? source.highlights : [];
        const id = `chat_fact_${Date.now()}`;
        const nodeSize = {
          w: 340,
          h: Math.min(260, Math.max(130, 82 + Math.ceil(content.length / 82) * 20)),
        };
        const absolutePos = anchorAtCenter(dropPos, nodeSize);
        const areaParent = findBestAreaParent(absolutePos, nodeSize, nodesRef.current);
        const finalPos = areaParent?.position ?? absolutePos;
        const node: any = {
          id,
          node_type: "fact",
          status: "found",
          title: parsed?.title || "Explanation",
          text: content,
          spec_title: "",
          properties: [],
          last_updated_run_id: "",
          filename: sourceFilename,
          page: Number.isFinite(sourcePage) && sourcePage > 0 ? sourcePage : 0,
          bbox: sourceBbox.length === 4 ? sourceBbox : [],
          highlights: sourceHighlights,
          fmu_filename: "",
          fmu_model_name: "",
          fmu_variables: [],
          fmu_param_values: {},
          plot_job_id: "",
          plot_fmu_filename: "",
          plot_signal_names: [],
          plot_stop_time: 10,
          funnel_label: "",
          area_label: "",
          area_width: 0,
          area_height: 0,
          model_label: "",
          width: nodeSize.w,
          height: nodeSize.h,
          parent_id: areaParent?.id ?? "",
        };
        commitPositionOverrides({ [id]: finalPos }, true);
        onAddNode?.(node, null);
      } catch {
        // ignore malformed chat payload
      }
      return;
    }

    // Handle gold region drops — add single region, then re-arrange all from same doc
    const regionPayload = e.dataTransfer.getData("application/anchor-region");
    if (regionPayload) {
      try {
        const region = JSON.parse(regionPayload);
        const nodeSize = NODE_SIZE.imageNode!;
        const cropUrl = region.crops?.svg
          ? `${API_URL}/api/documents/region-asset/${encodeURIComponent(region.slug)}/${region.crops.svg}`
          : region.crops?.png
          ? `${API_URL}/api/documents/region-asset/${encodeURIComponent(region.slug)}/${region.crops.png}`
          : undefined;

        // Add the single dragged region
        const id = `region_${Date.now()}`;
        const node: any = {
          id,
          node_type: "image",
          status: "found",
          title: region.title || "",
          text: region.description || "",
          spec_title: "", properties: [], last_updated_run_id: "",
          filename: region.filename || "", page: region.page || 0,
          bbox: region.bbox || [], highlights: [],
          fmu_filename: "", fmu_model_name: "", fmu_variables: [], fmu_param_values: {},
          plot_job_id: "", plot_fmu_filename: "", plot_signal_names: [], plot_stop_time: 10,
          funnel_label: "", area_label: "", area_width: 0, area_height: 0, model_label: "",
          image_filename: region.filename || "",
          image_page: region.page || 0,
          image_bbox: region.bbox || [],
          image_highlights: [],
          image_caption: region.title || "",
          image_url: cropUrl,
          width: nodeSize.w, height: nodeSize.h, parent_id: "",
        };
        const absolutePos = anchorAtCenter(dropPos, nodeSize);
        positionOverridesRef.current[id] = absolutePos;
        onAddNode?.(node, null);

        // Place in the next available grid slot to the right of the document node
        const fn = region.filename || "";
        const docNode = nodesRef.current.find(
          (n) => n.type === "documentNode" && (n.data as any)?.doc?.filename === fn
        );
        const existingSiblings = nodesRef.current.filter(
          (n) => n.type === "imageNode" && (n.data as any)?.node?.image_filename === fn
        );
        const slotIndex = existingSiblings.length; // new node is the Nth
        const gap = 20;
        const cellW = nodeSize.w + gap;
        const cellH = nodeSize.h + gap + 40; // extra for caption
        const cols = 2;
        const col = slotIndex % cols;
        const row = Math.floor(slotIndex / cols);
        // Anchor grid to the right of the document node
        const gridOriginX = docNode ? docNode.position.x + 210 : absolutePos.x;
        const gridOriginY = docNode ? docNode.position.y : absolutePos.y;
        const gridPos = { x: gridOriginX + col * cellW, y: gridOriginY + row * cellH };

        positionOverridesRef.current[id] = gridPos;
        commitPositionOverrides({ [id]: gridPos }, true);
      } catch {
        // ignore malformed region payload
      }
      return;
    }

    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;
    try {
      // Compute drop positions per file upfront
      const positions = files.map((file, index) => ({
        file,
        pos: anchorAtCenter(
          { x: dropPos.x + index * 36, y: dropPos.y + index * 28 },
          file.name.endsWith(".fmu") ? NODE_SIZE.fmuNode! : DOCUMENT_NODE_SIZE,
        ),
      }));

      const docIds = await Promise.all(positions.map(({ file, pos }) =>
        uploadCanvasFile(file, onFmuUploaded, pos),
      ));
      await refreshDocuments();

      // Add each uploaded doc to the canvas at its drop position
      const overrides: Record<string, { x: number; y: number }> = {};
      for (let i = 0; i < docIds.length; i++) {
        const docId = docIds[i];
        if (docId) {
          overrides[`__doc_${docId}`] = positions[i]!.pos;
        }
      }
      if (Object.keys(overrides).length) {
        commitPositionOverrides(overrides, true);
      }
      for (const docId of docIds) {
        if (docId) onAddDocToWorkspace?.(docId);
      }
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
        onContextMenu={(e) => e.preventDefault()}
      >
        {showInternalToolbar && (
          <LeftToolRail
            activeTool={activeTool}
            onChange={setActiveTool}
            onArrange={handleArrangeCanvas}
            openPalette={openPalette}
            onTogglePalette={(tab, anchorY) => {
              setOpenPalette(prev => prev === tab ? null : tab);
              setPaletteAnchorY(anchorY);
            }}
          />
        )}
        {showInternalToolbar && openPalette && (
          <ResourcePalette
            tab={openPalette}
            anchorY={paletteAnchorY}
            workspaceDocIds={workspaceDocIds ?? []}
            onAddDoc={(docId) => { onAddDocToWorkspace?.(docId); }}
            onAddFmu={(filename) => { onFmuFromLibrary?.(filename); }}
            onAddSnippet={(nodes, relations) => { onAddSnippet?.(nodes, relations); }}
            onClose={() => setOpenPalette(null)}
          />
        )}
        {showInternalToolbar && activeTool === "connect" && (
          <div className="absolute left-1/2 top-16 z-20 -translate-x-1/2 rounded-full border border-neutral-200/80 bg-white/90 px-3 py-1 text-[11px] text-neutral-500 shadow-sm backdrop-blur-md dark:border-neutral-700/80 dark:bg-neutral-900/90 dark:text-neutral-400">
            Drag from node handles to connect items
          </div>
        )}
        {showInternalToolbar && isInsertTool(activeTool) && (
          <div className="absolute left-1/2 top-16 z-20 -translate-x-1/2 rounded-full border border-neutral-200/80 bg-white/90 px-3 py-1 text-[11px] text-neutral-500 shadow-sm backdrop-blur-md dark:border-neutral-700/80 dark:bg-neutral-900/90 dark:text-neutral-400">
            Click and drag on the canvas to create a {activeTool}
          </div>
        )}
        {drawDraft && (
          <div
            className={`absolute z-20 pointer-events-none border-2 ${
              drawDraft.type === "area"
                ? "border-dashed border-indigo-500 bg-indigo-100/30 dark:bg-indigo-900/20 rounded-2xl"
                : drawDraft.type === "note"
                ? "border-amber-400 bg-amber-100/50 dark:bg-amber-900/30 rounded-sm"
                : drawDraft.type === "circle_shape" || drawDraft.type === "entity"
                ? "border-neutral-400 bg-neutral-100/30 dark:bg-neutral-800/30 rounded-full"
                : drawDraft.type === "diamond_shape" || drawDraft.type === "funnel"
                ? "border-neutral-400 bg-neutral-100/30 dark:bg-neutral-800/30 rounded-none"
                : drawDraft.type === "rich_text" || drawDraft.type === "fact"
                ? "border-neutral-300 border-dashed bg-transparent rounded-md"
                : "border-neutral-400 bg-neutral-100/30 dark:bg-neutral-800/30 rounded-md"
            }`}
            style={{
              left: Math.min(drawDraft.startClient.x, drawDraft.currentClient.x) - (rfContainerRef.current?.getBoundingClientRect().left ?? 0),
              top: Math.min(drawDraft.startClient.y, drawDraft.currentClient.y) - (rfContainerRef.current?.getBoundingClientRect().top ?? 0),
              width: Math.max(24, Math.abs(drawDraft.currentClient.x - drawDraft.startClient.x)),
              height: Math.max(24, Math.abs(drawDraft.currentClient.y - drawDraft.startClient.y)),
              clipPath: (drawDraft.type === "diamond_shape" || drawDraft.type === "funnel") ? "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" : undefined,
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
          onEdgesDelete={(deleted) => deleted.forEach((e) => {
            onDeleteEdge?.(e.source, e.target, e.sourceHandle ?? '', e.targetHandle ?? '');
          })}
          onConnectStart={onConnectStart}
          onConnectEnd={onConnectEnd}
          onConnect={onConnect}
          onNodeDoubleClick={onNodeDoubleClick}
          onPaneClick={() => {}}
          onSelectionStart={onSelectionStart}
          onSelectionChange={onSelectionChange}
          selectionMode={SelectionMode.Partial}
          selectionOnDrag={!isInsertTool(activeTool) && activeTool !== "connect"}
          panOnDrag={[1, 2]}
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
