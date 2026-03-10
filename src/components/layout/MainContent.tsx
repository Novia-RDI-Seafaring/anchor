import React, { useState } from 'react';
import { useApp } from '@/contexts/AppContext';
import { AgCard } from '../ui/AgComponents';
import { FileText, Database, LayoutDashboard, Network } from 'lucide-react';
import { useCopilotChat, useCoAgent } from "@copilotkit/react-core";
import { Message, TextMessage } from "@copilotkit/runtime-client-gql";
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
  const { visibleMessages = [] } = useCopilotChat() as any;
  const { activeConversationId, updateConversation, conversations } = useApp();
  const [activeTab, setActiveTab] = useState<TabId>('canvas');
  const [contextPdf, setContextPdf] = useState<{
    filename: string;
    page: number;
    highlights: PDFHighlight[];
  } | null>(null);
  const { state } = useCoAgent({
    name: "my_agent",
    initialState: { nodes: [], relations: [] }
  });
  const canvas = state as any;
  const sourceNodes = (canvas?.nodes || []).filter((node: any) => node?.node_type === 'source');
  const allNodes = canvas?.nodes || [];
  const allRelations = canvas?.relations || [];
  const nodeMap = new Map(allNodes.map((node: any) => [node.id, node]));
  const contextEvidence = sourceNodes.map((node: any) => {
    const parentIds = allRelations
      .filter((relation: any) => relation.to_id === node.id)
      .map((relation: any) => relation.from_id);
    const parents = parentIds
      .map((parentId: string) => nodeMap.get(parentId))
      .filter(Boolean);
    const primaryParent = parents[0];
    const parentLabel = primaryParent?.node_type === 'spec'
      ? (primaryParent.spec_title || 'Specifications')
      : (primaryParent?.text || primaryParent?.title || 'Evidence');
    const highlights: PDFHighlight[] = node.highlights && node.highlights.length > 0
      ? node.highlights
      : [{ page: node.page ?? 1, bbox: node.bbox ?? [] }];

    return {
      id: node.id,
      filename: node.filename,
      page: node.page ?? 1,
      bbox: node.bbox ?? [],
      highlights,
      previewUrl: buildEvidenceImageUrl(node.filename, node.page ?? 1, node.bbox ?? []),
      title: primaryParent?.node_type === 'spec' ? (primaryParent.spec_title || 'Specifications') : 'Fact evidence',
      summary: String(parentLabel || '').replace(/\s+/g, ' ').trim(),
      parentType: primaryParent?.node_type === 'spec' ? 'spec' : 'fact',
    };
  });

  // Use ref to track latest conversations without causing effect re-runs
  const conversationsRef = React.useRef(conversations);

  React.useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  // Persist messages and update title
  React.useEffect(() => {
    // 1. Basic Guard: No active conversation
    if (!activeConversationId) return;

    // Use ref to get latest conversations without dependency
    const currentConv = conversationsRef.current.find(c => c.id === activeConversationId);
    if (!currentConv) return;

    const currentMessages = currentConv.messages || [];

    // 2. Guard: Avoid overwriting populated conversation with empty state
    if (visibleMessages.length === 0 && currentMessages.length > 0) {
      return;
    }

    // 3. Optimization: Check if content actually changed
    if (currentMessages.length === visibleMessages.length) {
      const lastMsgIdx = visibleMessages.length - 1;
      if (lastMsgIdx >= 0) {
        const lastVisible = visibleMessages[lastMsgIdx] as any;
        const lastStored = currentMessages[lastMsgIdx];

        if (lastVisible?.id === lastStored?.id && lastVisible?.content === lastStored?.content) {
          return; // No change
        }
      } else {
        return; // Both empty
      }
    }

    const updates: any = {
      messages: visibleMessages.map((msg: Message) => {
        if (msg.isTextMessage()) {
          const textMsg = msg as TextMessage;
          return {
            id: msg.id,
            role: textMsg.role,
            content: textMsg.content,
            type: 'text'
          };
        }
        return msg;
      }),
      lastMessageAt: 'Just now',
      preview: `${visibleMessages.length} messages - Just now`
    };

    // 4. Auto-generate title from first user message
    if (currentConv.title === 'New Conversation' && visibleMessages.length > 0) {
      const firstUserMsg = visibleMessages.find((m: Message) => m.isTextMessage() && m.role === 'user');
      if (firstUserMsg) {
        const content = (firstUserMsg as TextMessage).content;
        updates.title = content.length > 30 ? content.substring(0, 30) + '...' : content;
      }
    }

    // Safe to call since updateConversation uses functional state updates
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

        {/* Canvas Tab — ReactFlow knowledge graph */}
        {activeTab === 'canvas' && (
          <CanvasGraph canvas={canvas} />
        )}

        {/* Facts Tab — list view of notes */}
        {activeTab === 'facts' && (
          <CanvasView canvas={canvas} />
        )}

        {/* Context Tab */}
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
