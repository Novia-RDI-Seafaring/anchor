import React, { useState, useEffect } from 'react';
import { useApp } from '@/contexts/AppContext';
import { AgCard } from '../ui/AgComponents';
import { FileText, Database, LayoutDashboard, Network } from 'lucide-react';
import { useCopilotChatInternal, useCoAgent } from "@copilotkit/react-core";
import { CanvasView } from '../canvas/CanvasView';
import { CanvasGraph } from '../canvas/CanvasGraph';
import { PDFModal, type PDFHighlight } from '../canvas/PDFModal';

type TabId = 'canvas' | 'facts' | 'context';
const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

function buildEvidenceImageUrl(filename: string, page: number, bbox: number[]): string {
  const [l = 0, t = 0, r = 0, b = 0] = bbox;
  if (!l && !t && !r && !b) {
    return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}`;
  }
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}&bbox_l=${l}&bbox_t=${t}&bbox_r=${r}&bbox_b=${b}`;
}

export const MainContent: React.FC = () => {
  const { messages: visibleMessages = [] } = useCopilotChatInternal();
  const { activeConversationId, updateConversation, conversations, loadConversationMessages } = useApp();
  const [activeTab, setActiveTab] = useState<TabId>('canvas');
  const [contextPdf, setContextPdf] = useState<{
    filename: string;
    page: number;
    highlights: PDFHighlight[];
  } | null>(null);
  const { activeDocumentId } = useApp();
  const { state, setState } = useCoAgent({
    name: "my_agent",
    initialState: { nodes: [], relations: [], active_document_id: null }
  });

  const canvas = state as any;

  // Node position overrides — persisted alongside canvas state
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const positionsRef = React.useRef(positions);
  useEffect(() => { positionsRef.current = positions; }, [positions]);

  // Sync document selection from UI into per-run agent state
  useEffect(() => {
    setState((prev: any) => ({ ...prev, active_document_id: activeDocumentId ?? null }));
  }, [activeDocumentId]);

  // Restore canvas state when switching conversations
  const prevConversationId = React.useRef<string | null>(null);
  useEffect(() => {
    if (!activeConversationId || activeConversationId === prevConversationId.current) return;
    prevConversationId.current = activeConversationId;

    loadConversationMessages(activeConversationId).then(({ canvas_state }) => {
      if (canvas_state && Object.keys(canvas_state).length > 0) {
        setState((prev: any) => ({ ...prev, ...canvas_state }));
        setPositions(canvas_state.positions ?? {});
      } else {
        setState(() => ({ nodes: [], relations: [], active_document_id: activeDocumentId ?? null }));
        setPositions({});
      }
    });
  }, [activeConversationId]);

  // Persist canvas state (nodes + relations + positions) when any of them change
  const canvasSaveTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!activeConversationId) return;
    if (canvasSaveTimer.current) clearTimeout(canvasSaveTimer.current);
    canvasSaveTimer.current = setTimeout(() => {
      const { nodes, relations } = canvas;
      updateConversation(activeConversationId, {
        canvas_state: { nodes, relations, positions: positionsRef.current },
      } as any);
    }, 1000);
    return () => { if (canvasSaveTimer.current) clearTimeout(canvasSaveTimer.current); };
  }, [canvas, activeConversationId]);

  // Separate debounced save for position-only changes (faster, doesn't wait for canvas change)
  const posSaveTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleSimulateComplete = React.useCallback((
    fmuNodeId: string, jobId: string, filename: string,
    signalNames: string[], paramValues: Record<string, string>, stopTime: number
  ) => {
    // Convert param strings to numbers (skip NaN)
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
    const relation = { from_id: fmuNodeId, to_id: plotNode.id, label: 'simulates' };
    setState((prev: any) => ({
      ...prev,
      nodes: [...(prev?.nodes ?? []), plotNode],
      relations: [...(prev?.relations ?? []), relation],
    }));
  }, [setState]);

  const handleDeleteNode = React.useCallback((nodeId: string) => {
    setState((prev: any) => ({
      ...prev,
      nodes: (prev?.nodes ?? []).filter((n: any) => n.id !== nodeId),
      relations: (prev?.relations ?? []).filter((r: any) => r.from_id !== nodeId && r.to_id !== nodeId),
    }));
  }, [setState]);

  const handleFmuUploaded = React.useCallback((payload: { filename: string; model_name: string; variables: any[] }) => {
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
    setState((prev: any) => ({ ...prev, nodes: [...(prev?.nodes ?? []), newNode] }));
  }, [setState]);

  const handlePositionsChange = React.useCallback((updated: Record<string, { x: number; y: number }>) => {
    setPositions(updated);
    if (!activeConversationId) return;
    if (posSaveTimer.current) clearTimeout(posSaveTimer.current);
    posSaveTimer.current = setTimeout(() => {
      const { nodes, relations } = canvas;
      updateConversation(activeConversationId, {
        canvas_state: { nodes, relations, positions: updated },
      } as any);
    }, 500);
  }, [activeConversationId, canvas, updateConversation]);

  const { documents } = useApp();
  const allNodes = canvas?.nodes || [];
  const allRelations = canvas?.relations || [];
  const nodeMap = new Map(allNodes.map((node: any) => [node.id, node]));

  // Evidence comes from relations that connect fact/spec nodes to document nodes
  const evidenceRelations = (allRelations as any[]).filter((r: any) =>
    r.to_id?.startsWith('__doc_') && r.page > 0
  );
  const contextEvidence = evidenceRelations.map((r: any) => {
    const parentNode: any = nodeMap.get(r.from_id);
    const doc = documents.find((d) => d.document_id === r.document_id);
    const filename = doc?.filename ?? '';
    const page = r.page ?? 1;
    const bbox = r.bbox ?? [];
    const highlights: PDFHighlight[] = r.highlights && r.highlights.length > 0
      ? r.highlights
      : [{ page, bbox }];
    const parentLabel = parentNode?.node_type === 'spec'
      ? (parentNode.spec_title || 'Specifications')
      : (parentNode?.text || parentNode?.title || 'Evidence');

    return {
      id: `${r.from_id}-${r.to_id}-${page}`,
      filename,
      page,
      bbox,
      highlights,
      previewUrl: buildEvidenceImageUrl(filename, page, bbox),
      title: parentNode?.node_type === 'spec' ? (parentNode.spec_title || 'Specifications') : 'Fact evidence',
      summary: String(parentLabel || '').replace(/\s+/g, ' ').trim(),
      parentType: parentNode?.node_type === 'spec' ? 'spec' : 'fact',
    };
  });

  // Use ref to track latest conversations without causing effect re-runs
  const conversationsRef = React.useRef(conversations);
  React.useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  // Track when we last switched conversations — don't persist on the first render after a switch
  const lastSavedConversationId = React.useRef<string | null>(null);

  // Persist messages and update title
  React.useEffect(() => {
    if (!activeConversationId) return;

    // Skip first render after switching conversations — visibleMessages still has old thread's messages
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
        const lastVisible = visibleMessages[lastMsgIdx] as any;
        const lastStored = currentMessages[lastMsgIdx] as any;
        if (lastVisible?.id === lastStored?.id && lastVisible?.content === lastStored?.content) return;
      } else {
        return;
      }
    }

    const updates: any = {
      messages: visibleMessages.map((msg: any) => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
        type: 'text',
      })),
      lastMessageAt: 'Just now',
      preview: `${visibleMessages.length} messages - Just now`
    };

    if (currentConv.title === 'New Conversation' && visibleMessages.length > 0) {
      const firstUserMsg = visibleMessages.find((m: any) => m.role === 'user');
      if (firstUserMsg) {
        const content = firstUserMsg.content ?? '';
        updates.title = content.length > 30 ? content.substring(0, 30) + '...' : content;
      }
    }

    updateConversation(activeConversationId, updates);
  }, [visibleMessages, activeConversationId, updateConversation]);

  return (
    <div className="flex-1 h-full bg-neutral-50/50 dark:bg-neutral-950 overflow-y-auto p-4 md:p-8 scroll-smooth border-r border-neutral-200 dark:border-neutral-800">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header Section */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold text-neutral-900 dark:text-white mb-1">Evidence Workspace</h1>
            <p className="text-neutral-500 dark:text-neutral-400 text-sm">Cross-check retrieved facts against source-backed evidence here.</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-neutral-100 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg p-1 w-fit">
          {(
            [
              { id: 'canvas', icon: <Network size={14} />, label: 'Canvas' },
              { id: 'facts',  icon: <LayoutDashboard size={14} />, label: 'Facts' },
              { id: 'context', icon: <Database size={14} />, label: 'Context' },
            ] as const
          ).map(({ id, icon, label }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === id
                  ? 'bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white shadow-sm'
                  : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              {icon}
              {label}
              {id !== 'context' && canvas?.nodes?.length > 0 && (
                <span className="text-[10px] bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded-full">
                  {canvas.nodes.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {activeTab === 'canvas' && <CanvasGraph canvas={canvas} initialPositions={positions} onPositionsChange={handlePositionsChange} onFmuUploaded={handleFmuUploaded} onSimulateComplete={handleSimulateComplete} onDeleteNode={handleDeleteNode} />}
        {activeTab === 'facts' && <CanvasView canvas={canvas} />}

        {activeTab === 'context' && (
          <div className="space-y-6">
            {contextEvidence.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {contextEvidence.map((evidence: any) => (
                  <AgCard
                    key={evidence.id}
                    className="overflow-hidden p-0 hover:shadow-md transition-all duration-200 group border-neutral-200/60 dark:border-neutral-800"
                  >
                    <button
                      onClick={() => setContextPdf({
                        filename: evidence.filename,
                        page: evidence.page,
                        highlights: evidence.highlights,
                      })}
                      className="block w-full text-left"
                    >
                      <div className="aspect-[4/3] bg-neutral-100 dark:bg-neutral-900 overflow-hidden border-b border-neutral-200 dark:border-neutral-800">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={evidence.previewUrl}
                          alt={`${evidence.filename} page ${evidence.page}`}
                          className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform"
                          loading="lazy"
                        />
                      </div>
                      <div className="p-4 space-y-2">
                        <div className="flex justify-between items-start gap-2">
                          <div className="min-w-0">
                            <h3 className="font-medium text-neutral-900 dark:text-white truncate" title={evidence.title}>
                              {evidence.title}
                            </h3>
                            <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate" title={evidence.filename}>
                              {evidence.filename} · p.{evidence.page}
                            </p>
                          </div>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full shrink-0 ${
                            evidence.parentType === 'spec'
                              ? 'bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300'
                              : 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
                          }`}>
                            {evidence.parentType}
                          </span>
                        </div>
                        <p className="text-xs text-neutral-600 dark:text-neutral-300 line-clamp-3">
                          {evidence.summary}
                        </p>
                      </div>
                    </button>
                  </AgCard>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <AgCard className="p-4 border-neutral-200/60 dark:border-neutral-800 opacity-50">
                  <div className="flex justify-between items-start mb-3">
                    <div className="h-10 w-10 bg-neutral-100 dark:bg-neutral-800 rounded-lg flex items-center justify-center">
                      <Database size={20} className="text-neutral-400" />
                    </div>
                  </div>
                  <h3 className="font-medium text-neutral-900 dark:text-white">No Context</h3>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                    Ask a technical question to populate source evidence previews here.
                  </p>
                </AgCard>
              </div>
            )}
          </div>
        )}

      </div>
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
