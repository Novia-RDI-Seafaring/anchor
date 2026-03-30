import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useApp } from '@/contexts/AppContext';
import { AgCard } from '../ui/AgComponents';
import { FileText, Database, LayoutDashboard, Network, BookOpen, X, Activity, Plus } from 'lucide-react';
import { useCopilotChatInternal, useCoAgent } from "@copilotkit/react-core";
import { CanvasView } from '../canvas/CanvasView';
import { CanvasGraph } from '../canvas/CanvasGraph';
import { PDFModal, type PDFHighlight } from '../canvas/PDFModal';
import { LibraryDrawer } from './LibraryDrawer';
import { RunsPanel } from './RunsPanel';
import { useSession } from 'next-auth/react';
import { API_URL } from '@/lib/api-config';

type TabId = 'canvas' | 'facts' | 'context' | 'runs';

type CanvasState = {
  nodes: any[];
  relations: any[];
  active_document_id: string | null;
  workspace_doc_ids?: string[];
};

// A named canvas tab — stores the saved state of non-active tabs
type CanvasTab = {
  id: string;
  name: string;
  nodes: any[];
  relations: any[];
  positions: Record<string, { x: number; y: number }>;
};

function buildEvidenceImageUrl(filename: string, page: number, bbox: number[]): string {
  const [l = 0, t = 0, r = 0, b = 0] = bbox;
  if (!l && !t && !r && !b) {
    return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}`;
  }
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}&bbox_l=${l}&bbox_t=${t}&bbox_r=${r}&bbox_b=${b}`;
}

function makeTabId() { return `cv_${Date.now()}`; }

export const MainContent: React.FC = () => {
  const { messages: visibleMessages = [] } = useCopilotChatInternal();
  const {
    activeConversationId,
    updateConversation,
    conversations,
    loadConversationMessages,
    activeDocumentId,
    documents,
  } = useApp();
  const { data: session } = useSession();
  const userId = (session?.user as any)?.id ?? 'local-dev-user';
  const userHeaders = { 'x-user-id': userId };
  const [activeTab, setActiveTab] = useState<TabId>('canvas');
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [contextPdf, setContextPdf] = useState<{
    filename: string;
    page: number;
    highlights: PDFHighlight[];
  } | null>(null);
  const { state, setState } = useCoAgent({
    name: "my_agent",
    initialState: { nodes: [], relations: [], active_document_id: null as string | null } as CanvasState
  });

  const canvas = state as any;

  // ── Multi-canvas tabs ──────────────────────────────────────────────────────
  // `canvasTabs` holds metadata + saved state for ALL tabs.
  // The active tab's nodes/relations live in coagent state (not duplicated here).
  const [canvasTabs, setCanvasTabs] = useState<CanvasTab[]>([
    { id: 'default', name: 'Canvas 1', nodes: [], relations: [], positions: {} },
  ]);
  const [activeCanvasId, setActiveCanvasId] = useState<string>('default');

  // Positions for the currently active canvas
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const positionsRef = useRef(positions);
  useEffect(() => { positionsRef.current = positions; }, [positions]);

  // Keep ref to canvasTabs for use inside callbacks without stale closure
  const canvasTabsRef = useRef(canvasTabs);
  useEffect(() => { canvasTabsRef.current = canvasTabs; }, [canvasTabs]);
  const activeCanvasIdRef = useRef(activeCanvasId);
  useEffect(() => { activeCanvasIdRef.current = activeCanvasId; }, [activeCanvasId]);

  // Sync document selection from UI into per-run agent state
  useEffect(() => {
    setState((prev: any) => ({ ...prev, active_document_id: activeDocumentId ?? null }));
  }, [activeDocumentId]);

  // ── Restore canvas state when switching conversations ───────────────────────
  const prevConversationId = useRef<string | null>(null);
  useEffect(() => {
    if (!activeConversationId || activeConversationId === prevConversationId.current) return;
    prevConversationId.current = activeConversationId;

    loadConversationMessages(activeConversationId).then(({ canvas_state }) => {
      if (canvas_state && Object.keys(canvas_state).length > 0) {
        if (canvas_state.tabs && Array.isArray(canvas_state.tabs)) {
          // New multi-canvas format
          const tabs: CanvasTab[] = canvas_state.tabs;
          const aid = canvas_state.activeTabId ?? tabs[0]?.id ?? 'default';
          const activeTabData = tabs.find(t => t.id === aid) ?? tabs[0];
          setCanvasTabs(tabs);
          setActiveCanvasId(aid);
          setPositions(activeTabData?.positions ?? {});
          setState((prev: any) => ({
            ...prev,
            nodes: activeTabData?.nodes ?? [],
            relations: activeTabData?.relations ?? [],
            workspace_doc_ids: canvas_state.workspace_doc_ids ?? prev.workspace_doc_ids,
          }));
        } else {
          // Legacy single-canvas format — wrap in a tab
          const tab: CanvasTab = {
            id: 'default',
            name: 'Canvas 1',
            nodes: canvas_state.nodes ?? [],
            relations: canvas_state.relations ?? [],
            positions: canvas_state.positions ?? {},
          };
          setCanvasTabs([tab]);
          setActiveCanvasId('default');
          setPositions(tab.positions);
          setState((prev: any) => ({
            ...prev,
            nodes: tab.nodes,
            relations: tab.relations,
            workspace_doc_ids: canvas_state.workspace_doc_ids ?? prev.workspace_doc_ids,
          }));
        }
      } else {
        const tab: CanvasTab = { id: 'default', name: 'Canvas 1', nodes: [], relations: [], positions: {} };
        setCanvasTabs([tab]);
        setActiveCanvasId('default');
        setPositions({});
        setState({ nodes: [], relations: [], active_document_id: activeDocumentId ?? null } as CanvasState);
      }
    });
  }, [activeConversationId]);

  // ── Helpers to build the canvas_state payload to persist ───────────────────
  // We need a function (not just state) so we can call it with latest values
  const buildCanvasStatePayload = useCallback((
    tabs: CanvasTab[],
    aid: string,
    activeNodes: any[],
    activeRelations: any[],
    activePositions: Record<string, { x: number; y: number }>,
    wsDocIds: string[],
  ) => {
    // Merge the live coagent state back into the active tab slot
    const merged = tabs.map(t =>
      t.id === aid
        ? { ...t, nodes: activeNodes, relations: activeRelations, positions: activePositions }
        : t
    );
    return {
      tabs: merged,
      activeTabId: aid,
      workspace_doc_ids: wsDocIds,
    };
  }, []);

  // ── Persist canvas state on change ─────────────────────────────────────────
  const canvasSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!activeConversationId) return;
    if (canvasSaveTimer.current) clearTimeout(canvasSaveTimer.current);
    canvasSaveTimer.current = setTimeout(() => {
      const payload = buildCanvasStatePayload(
        canvasTabsRef.current,
        activeCanvasIdRef.current,
        canvas?.nodes ?? [],
        canvas?.relations ?? [],
        positionsRef.current,
        canvas?.workspace_doc_ids ?? [],
      );
      updateConversation(activeConversationId, { canvas_state: payload } as any);
    }, 1000);
    return () => { if (canvasSaveTimer.current) clearTimeout(canvasSaveTimer.current); };
  }, [canvas, activeConversationId, canvasTabs, activeCanvasId]);

  // ── Canvas tab switch ───────────────────────────────────────────────────────
  const switchCanvasTab = useCallback((newId: string) => {
    if (newId === activeCanvasIdRef.current) return;

    // Save current coagent state into the current tab slot
    setCanvasTabs(prev => prev.map(t =>
      t.id === activeCanvasIdRef.current
        ? { ...t, nodes: (canvas as any)?.nodes ?? [], relations: (canvas as any)?.relations ?? [], positions: positionsRef.current }
        : t
    ));

    // Load new tab
    const newTab = canvasTabsRef.current.find(t => t.id === newId);
    if (newTab) {
      setState((prev: any) => ({ ...prev, nodes: newTab.nodes, relations: newTab.relations }));
      setPositions(newTab.positions);
    }
    setActiveCanvasId(newId);
  }, [canvas, setState]);

  // ── Create a new canvas tab ─────────────────────────────────────────────────
  const addCanvasTab = useCallback(() => {
    // Save current tab first
    setCanvasTabs(prev => {
      const saved = prev.map(t =>
        t.id === activeCanvasIdRef.current
          ? { ...t, nodes: (canvas as any)?.nodes ?? [], relations: (canvas as any)?.relations ?? [], positions: positionsRef.current }
          : t
      );
      const newId = makeTabId();
      const newTab: CanvasTab = { id: newId, name: `Canvas ${saved.length + 1}`, nodes: [], relations: [], positions: {} };
      // Switch to new tab
      setTimeout(() => {
        setState((prev: any) => ({ ...prev, nodes: [], relations: [] }));
        setPositions({});
        setActiveCanvasId(newId);
      }, 0);
      return [...saved, newTab];
    });
  }, [canvas, setState]);

  // ── Close a canvas tab ──────────────────────────────────────────────────────
  const closeCanvasTab = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setCanvasTabs(prev => {
      if (prev.length <= 1) return prev; // keep at least one
      const next = prev.filter(t => t.id !== id);
      if (id === activeCanvasIdRef.current) {
        const newActive = next[next.length - 1] ?? next[0];
        if (newActive) {
          setState((p: any) => ({ ...p, nodes: newActive.nodes, relations: newActive.relations }));
          setPositions(newActive.positions);
          setActiveCanvasId(newActive.id);
        }
      }
      return next;
    });
  }, [setState]);

  // ── Position save (debounced, separate from full canvas save) ──────────────
  const posSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlePositionsChange = useCallback((updated: Record<string, { x: number; y: number }>) => {
    setPositions(updated);
    if (!activeConversationId) return;
    if (posSaveTimer.current) clearTimeout(posSaveTimer.current);
    posSaveTimer.current = setTimeout(() => {
      const payload = buildCanvasStatePayload(
        canvasTabsRef.current,
        activeCanvasIdRef.current,
        canvas?.nodes ?? [],
        canvas?.relations ?? [],
        updated,
        canvas?.workspace_doc_ids ?? [],
      );
      updateConversation(activeConversationId, { canvas_state: payload } as any);
    }, 500);
  }, [activeConversationId, canvas, updateConversation, buildCanvasStatePayload]);

  // ── Snippet save ────────────────────────────────────────────────────────────
  const handleSaveSelection = useCallback(async (selectedNodeIds: string[], name?: string) => {
    const allNodes: any[] = canvas?.nodes ?? [];
    const allRels: any[] = canvas?.relations ?? [];
    const nodeSet = new Set(selectedNodeIds);
    const nodes = allNodes.filter(n => nodeSet.has(n.id));
    const relations = allRels.filter(r => nodeSet.has(r.from_id) && nodeSet.has(r.to_id));
    const snippetName = name || (nodes[0]?.title || nodes[0]?.text || 'Snippet').slice(0, 40);
    const res = await fetch(`${API_URL}/api/snippets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...userHeaders },
      body: JSON.stringify({ id: crypto.randomUUID(), name: snippetName, nodes, relations }),
    }).catch(() => null);
    if (!res?.ok) console.error('[snippets] Save failed:', res?.status, res?.statusText);
  }, [canvas, userHeaders]);

  // ── Simulate complete handler ───────────────────────────────────────────────
  const handleSimulateComplete = useCallback((
    fmuNodeId: string, jobId: string, filename: string,
    signalNames: string[], paramValues: Record<string, string>, stopTime: number
  ) => {
    const numericParams: Record<string, number> = {};
    Object.entries(paramValues).forEach(([k, v]) => {
      const n = parseFloat(v); if (!isNaN(n)) numericParams[k] = n;
    });
    const plotNode = {
      id: `plot_${Date.now()}`,
      node_type: 'plot',
      status: 'found',
      title: `${filename} — simulation`,
      plot_job_id: jobId,
      plot_fmu_filename: filename,
      plot_signal_names: signalNames,
      plot_stop_time: stopTime,
      plot_param_values: numericParams,
      last_updated_run_id: '',
      text: '', spec_title: '', properties: [], fmu_filename: '', fmu_model_name: '',
      fmu_variables: [], fmu_param_values: {}, filename: '', page: 0, bbox: [], highlights: [],
    };
    const relation = { from_id: fmuNodeId, to_id: plotNode.id, label: Object.entries(numericParams).map(([k, v]) => `${k}=${v}`).join(', ') || 'simulate' };
    const currentCanvas = canvas as any;
    setState({
      ...currentCanvas,
      nodes: [...(currentCanvas?.nodes ?? []), plotNode],
      relations: [...(currentCanvas?.relations ?? []), relation],
    });
  }, [setState, canvas]);

  const handleDeleteNode = useCallback((nodeId: string) => {
    const c = canvas as any;
    setState({ ...c, nodes: (c?.nodes ?? []).filter((n: any) => n.id !== nodeId), relations: (c?.relations ?? []).filter((r: any) => r.from_id !== nodeId && r.to_id !== nodeId) });
  }, [setState, canvas]);

  const handleAddNode = useCallback((node: any, relation: { from_id: string; to_id: string; label: string } | null) => {
    const c = canvas as any;
    setState({ ...c, nodes: [...(c?.nodes ?? []), node], relations: relation ? [...(c?.relations ?? []), relation] : (c?.relations ?? []) });
  }, [setState, canvas]);

  const handleSetNodeColor = useCallback((nodeId: string, color: string) => {
    const c = canvas as any;
    setState({ ...c, nodes: (c?.nodes ?? []).map((n: any) => n.id === nodeId ? { ...n, color: color || undefined } : n) });
  }, [setState, canvas]);

  const handleAddEdge = useCallback((fromId: string, toId: string, label: string) => {
    const c = canvas as any;
    const rels = c?.relations ?? [];
    if (rels.some((r: any) => r.from_id === fromId && r.to_id === toId)) return;
    setState({ ...c, relations: [...rels, { from_id: fromId, to_id: toId, label }] });
  }, [setState, canvas]);

  const handleFmuUploaded = useCallback((payload: { filename: string; model_name: string; variables: any[] }) => {
    const newNode = {
      id: `fmu_${Date.now()}`,
      node_type: 'fmu',
      status: 'found',
      title: payload.model_name || payload.filename,
      fmu_filename: payload.filename,
      fmu_model_name: payload.model_name,
      fmu_variables: payload.variables,
      fmu_param_values: {},
      last_updated_run_id: '',
      text: '', spec_title: '', properties: [], filename: '', page: 0, bbox: [], highlights: [],
      plot_job_id: '', plot_fmu_filename: '', plot_signal_names: [], plot_stop_time: 10,
    };
    const c = canvas as any;
    setState({ ...c, nodes: [...(c?.nodes ?? []), newNode] });
  }, [setState, canvas]);

  const handleAddDocToWorkspace = useCallback((docId: string) => {
    const c = canvas as any;
    const existing: string[] = c?.workspace_doc_ids ?? [];
    if (existing.includes(docId)) return;
    setState({ ...c, workspace_doc_ids: [...existing, docId] });
  }, [setState, canvas]);

  const handleAddSnippet = useCallback((snippetNodes: any[], snippetRelations: any[]) => {
    // Remap node IDs to fresh ones to avoid collisions
    const idMap = new Map<string, string>();
    const newNodes = snippetNodes.map(n => {
      const newId = `sn_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      idMap.set(n.id, newId);
      return { ...n, id: newId };
    });
    const newRelations = snippetRelations.map(r => ({
      ...r,
      from_id: idMap.get(r.from_id) ?? r.from_id,
      to_id: idMap.get(r.to_id) ?? r.to_id,
    }));
    const c = canvas as any;
    setState({ ...c, nodes: [...(c?.nodes ?? []), ...newNodes], relations: [...(c?.relations ?? []), ...newRelations] });
  }, [canvas, setState]);

  const handleFmuFromLibrary = useCallback(async (filename: string) => {
    const c = canvas as any;
    if ((c?.nodes ?? []).some((n: any) => n.node_type === 'fmu' && n.fmu_filename === filename)) return;
    try {
      const res = await fetch(`${API_URL}/api/fmu/inspect/${encodeURIComponent(filename)}`);
      if (!res.ok) return;
      const data = await res.json();
      handleFmuUploaded({ filename, model_name: data.model_name, variables: data.variables ?? [] });
    } catch { /* ignore */ }
  }, [canvas, handleFmuUploaded]);

  // ── Evidence data ────────────────────────────────────────────────────────────
  const allNodes = canvas?.nodes || [];
  const allRelations = canvas?.relations || [];
  const nodeMap = new Map(allNodes.map((node: any) => [node.id, node]));
  const evidenceRelations = (allRelations as any[]).filter((r: any) => r.to_id?.startsWith('__doc_') && r.page > 0);
  const contextEvidence = evidenceRelations.map((r: any) => {
    const parentNode: any = nodeMap.get(r.from_id);
    const doc = documents.find((d) => d.document_id === r.document_id);
    const filename = doc?.filename ?? '';
    const page = r.page ?? 1;
    const bbox = r.bbox ?? [];
    const highlights: PDFHighlight[] = r.highlights?.length > 0 ? r.highlights : [{ page, bbox }];
    const parentLabel = parentNode?.node_type === 'spec' ? (parentNode.spec_title || 'Specifications') : (parentNode?.text || parentNode?.title || 'Evidence');
    return {
      id: `${r.from_id}-${r.to_id}-${page}`,
      filename, page, bbox, highlights,
      previewUrl: buildEvidenceImageUrl(filename, page, bbox),
      title: parentNode?.node_type === 'spec' ? (parentNode.spec_title || 'Specifications') : 'Fact evidence',
      summary: String(parentLabel || '').replace(/\s+/g, ' ').trim(),
      parentType: parentNode?.node_type === 'spec' ? 'spec' : 'fact',
    };
  });

  // ── Message persistence ──────────────────────────────────────────────────────
  const conversationsRef = useRef(conversations);
  useEffect(() => { conversationsRef.current = conversations; }, [conversations]);
  const lastSavedConversationId = useRef<string | null>(null);

  useEffect(() => {
    if (!activeConversationId) return;
    if (lastSavedConversationId.current !== activeConversationId) {
      lastSavedConversationId.current = activeConversationId;
      return;
    }
    const currentConv = conversationsRef.current.find(c => c.id === activeConversationId);
    if (!currentConv) return;
    const currentMessages = currentConv.messages || [];
    if (visibleMessages.length === 0 && currentMessages.length > 0) return;
    if (currentMessages.length === visibleMessages.length) {
      const lastMsgIdx = visibleMessages.length - 1;
      if (lastMsgIdx >= 0) {
        const lv = visibleMessages[lastMsgIdx] as any;
        const ls = currentMessages[lastMsgIdx] as any;
        if (lv?.id === ls?.id && lv?.content === ls?.content) return;
      } else { return; }
    }
    const updates: any = {
      messages: visibleMessages.map((msg: any) => ({ id: msg.id, role: msg.role, content: msg.content, type: 'text' })),
      lastMessageAt: 'Just now',
      preview: `${visibleMessages.length} messages - Just now`,
    };
    if (currentConv.title === 'New Conversation' && visibleMessages.length > 0) {
      const firstUserMsg = visibleMessages.find((m: any) => m.role === 'user');
      if (firstUserMsg) {
        const rawContent = firstUserMsg.content;
        const content = typeof rawContent === 'string' ? rawContent
          : Array.isArray(rawContent) ? rawContent.map((part: any) => part?.type === 'text' ? part.text : '').join(' ').trim() : '';
        updates.title = content.length > 30 ? content.substring(0, 30) + '...' : content;
      }
    }
    updateConversation(activeConversationId, updates);
  }, [visibleMessages, activeConversationId, updateConversation]);

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div className="flex-1 h-full relative overflow-hidden bg-neutral-50 dark:bg-neutral-950">

      {/* Full-screen canvas */}
      <CanvasGraph
        canvas={canvas}
        initialPositions={positions}
        onPositionsChange={handlePositionsChange}
        onFmuUploaded={handleFmuUploaded}
        onSimulateComplete={handleSimulateComplete}
        onDeleteNode={handleDeleteNode}
        onAddNode={handleAddNode}
        onAddEdge={handleAddEdge}
        onSetNodeColor={handleSetNodeColor}
        workspaceDocIds={canvas?.workspace_doc_ids ?? []}
        onAddDocToWorkspace={handleAddDocToWorkspace}
        onFmuFromLibrary={handleFmuFromLibrary}
        onSaveSelection={handleSaveSelection}
      />

      {/* ── Canvas tab bar — top-left ─────────────────────────────────── */}
      <div className="absolute top-3 left-4 z-10 flex items-center gap-1">
        {/* View tabs */}
        <div className="flex items-center gap-1 bg-white/90 dark:bg-neutral-900/90 backdrop-blur-sm border border-neutral-200 dark:border-neutral-700 rounded-lg p-1 shadow-sm">
          {(
            [
              { id: 'canvas', icon: <Network size={13} />, label: 'Canvas' },
              { id: 'facts',  icon: <LayoutDashboard size={13} />, label: 'Facts' },
              { id: 'context', icon: <Database size={13} />, label: 'Context' },
              { id: 'runs', icon: <Activity size={13} />, label: 'Runs' },
            ] as const
          ).map(({ id, icon, label }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeTab === id
                  ? 'bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-white shadow-sm'
                  : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              {icon}
              {label}
              {(id === 'canvas' || id === 'facts') && (canvas?.nodes?.length ?? 0) > 0 && (
                <span className="text-[10px] bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded-full">
                  {canvas.nodes.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Canvas tabs — only visible in canvas view */}
        {activeTab === 'canvas' && (
          <div className="flex items-center gap-0.5 bg-white/90 dark:bg-neutral-900/90 backdrop-blur-sm border border-neutral-200 dark:border-neutral-700 rounded-lg p-1 shadow-sm">
            {canvasTabs.map(tab => (
              <div
                key={tab.id}
                onClick={() => switchCanvasTab(tab.id)}
                className={`group flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors select-none ${
                  tab.id === activeCanvasId
                    ? 'bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-white shadow-sm'
                    : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800/50'
                }`}
              >
                <span className="max-w-[80px] truncate">{tab.name}</span>
                {canvasTabs.length > 1 && (
                  <button
                    onClick={e => closeCanvasTab(tab.id, e)}
                    className="opacity-0 group-hover:opacity-100 hover:text-red-500 transition-opacity -mr-0.5 rounded"
                  >
                    <X size={10} />
                  </button>
                )}
              </div>
            ))}
            <button
              onClick={addCanvasTab}
              className="flex items-center justify-center p-1.5 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              title="New canvas"
            >
              <Plus size={12} />
            </button>
          </div>
        )}
      </div>

      {/* Library toggle — top-right */}
      <button
        onClick={() => setLibraryOpen(v => !v)}
        className={`absolute top-3 right-4 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border shadow-sm transition-colors ${
          libraryOpen
            ? 'bg-indigo-600 dark:bg-indigo-500 text-white border-indigo-700 dark:border-indigo-600'
            : 'bg-white/90 dark:bg-neutral-900/90 backdrop-blur-sm border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200'
        }`}
      >
        <BookOpen size={13} />
        Library
        {(canvas?.workspace_doc_ids?.length ?? 0) > 0 && (
          <span className="bg-indigo-100 dark:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded-full text-[10px]">
            {canvas.workspace_doc_ids.length}
          </span>
        )}
      </button>

      {/* Facts overlay */}
      {activeTab === 'facts' && (
        <div className="absolute inset-0 z-10 bg-white/96 dark:bg-neutral-950/96 backdrop-blur-sm overflow-y-auto">
          <div className="max-w-5xl mx-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Facts</h2>
              <button onClick={() => setActiveTab('canvas')} className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500"><X size={16} /></button>
            </div>
            <CanvasView canvas={canvas} />
          </div>
        </div>
      )}

      {/* Context overlay */}
      {activeTab === 'context' && (
        <div className="absolute inset-0 z-10 bg-white/96 dark:bg-neutral-950/96 backdrop-blur-sm overflow-y-auto">
          <div className="max-w-5xl mx-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Evidence Context</h2>
              <button onClick={() => setActiveTab('canvas')} className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500"><X size={16} /></button>
            </div>
            {contextEvidence.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {contextEvidence.map((evidence: any) => (
                  <AgCard key={evidence.id} className="overflow-hidden p-0 hover:shadow-md transition-all duration-200 group border-neutral-200/60 dark:border-neutral-800">
                    <button onClick={() => setContextPdf({ filename: evidence.filename, page: evidence.page, highlights: evidence.highlights })} className="block w-full text-left">
                      <div className="aspect-[4/3] bg-neutral-100 dark:bg-neutral-900 overflow-hidden border-b border-neutral-200 dark:border-neutral-800">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={evidence.previewUrl} alt={`${evidence.filename} page ${evidence.page}`} className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform" loading="lazy" />
                      </div>
                      <div className="p-4 space-y-2">
                        <div className="flex justify-between items-start gap-2">
                          <div className="min-w-0">
                            <h3 className="font-medium text-neutral-900 dark:text-white truncate" title={evidence.title}>{evidence.title}</h3>
                            <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate" title={evidence.filename}>{evidence.filename} · p.{evidence.page}</p>
                          </div>
                        </div>
                        <p className="text-xs text-neutral-600 dark:text-neutral-400 line-clamp-3">{evidence.summary}</p>
                      </div>
                    </button>
                  </AgCard>
                ))}
              </div>
            ) : (
              <p className="text-sm text-neutral-400 dark:text-neutral-500">No evidence collected yet.</p>
            )}
          </div>
        </div>
      )}

      {/* Runs overlay */}
      {activeTab === 'runs' && (
        <RunsPanel onClose={() => setActiveTab('canvas')} />
      )}

      {/* Library drawer */}
      <LibraryDrawer
        open={libraryOpen}
        onClose={() => setLibraryOpen(false)}
        workspaceDocIds={canvas?.workspace_doc_ids ?? []}
        onAddDoc={handleAddDocToWorkspace}
        onAddFmu={handleFmuFromLibrary}
        onAddSnippet={handleAddSnippet}
      />

      {/* Context PDF modal */}
      {contextPdf && (
        <PDFModal
          filename={contextPdf.filename}
          initialPage={contextPdf.page}
          highlights={contextPdf.highlights}
          onClose={() => setContextPdf(null)}
        />
      )}
    </div>
  );
};
