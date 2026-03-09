import React, { useMemo, useState } from 'react';
import { useApp } from '@/contexts/AppContext';
import { AgCard, AgButton, AgBadge } from '../ui/AgComponents';
import { BarChart3, FileText, MoreHorizontal, Share2, Database, ExternalLink, LayoutDashboard, Network } from 'lucide-react';
import { useCopilotChat, useCoAgent } from "@copilotkit/react-core";
import { Message, TextMessage } from "@copilotkit/runtime-client-gql";
import { ComponentRenderer } from '../kb/ComponentRenderer';
import { CanvasView } from '../canvas/CanvasView';
import { CanvasGraph } from '../canvas/CanvasGraph';

interface Chunk {
  id?: string;
  content: string;
  filename: string;
  similarity: number;
  document_id?: string;
  page_numbers?: number[];
  section_path?: string[];
  citation?: {
    document_id?: string;
    filename?: string;
    chunk_id?: string;
    page_numbers?: number[];
    section_path?: string[];
  };
  provenance?: any;
  metadata: any;
}

interface ToolResult {
  chunks: Chunk[];
  sources: string[];
}

type TabId = 'canvas' | 'facts' | 'context';

export const MainContent: React.FC = () => {
  const { visibleMessages = [] } = useCopilotChat() as any;
  const { activeConversationId, updateConversation, conversations } = useApp();
  const [activeTab, setActiveTab] = useState<TabId>('canvas');
  const { state } = useCoAgent({
    name: "my_agent",
    initialState: { notes: [], active_ui_components: [], render_mode: "auto" }
  });
  const uiComponents = (state as any)?.active_ui_components || [];
  const canvas = state as any; // shape: { notes: Note[] }

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

  // Extract RAG data from agent state instead of messages
  const ragData = useMemo(() => {
    // Get sources and chunks from agent state (with type assertion)
    const agentState = state as any; // State type varies, use any for flexibility
    const sources = agentState?.current_sources || [];
    const chunks = agentState?.last_chunks || [];
    const retrievalMeta = agentState?.last_retrieval_meta || null;

    console.log("Agent state - sources:", sources, "chunks:", chunks?.length);

    if (sources.length > 0 || chunks.length > 0) {
      return {
        sources: sources,
        chunks: chunks,
        retrievalMeta: retrievalMeta,
      };
    }

    return null;
  }, [state]);

  return (
    <div className="flex-1 h-full bg-neutral-50/50 dark:bg-neutral-950 overflow-y-auto p-4 md:p-8 scroll-smooth border-r border-neutral-200 dark:border-neutral-800">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header Section */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold text-neutral-900 dark:text-white mb-1">Project Workspace</h1>
            <p className="text-neutral-500 dark:text-neutral-400 text-sm">Sourced facts and retrieved documents appear here.</p>
          </div>
          <div className="flex gap-2">
            <AgButton variant="secondary" size="sm" className="hidden md:flex gap-2">
              <Share2 size={16} />
              Share
            </AgButton>
            <AgButton variant="icon" size="sm">
              <MoreHorizontal size={20} />
            </AgButton>
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
            {/* Sources Grid */}
            {ragData?.sources && ragData.sources.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {ragData.sources.map((source: string, idx: number) => (
                  <AgCard key={idx} className="p-4 hover:shadow-md transition-all duration-200 cursor-pointer group border-neutral-200/60 dark:border-neutral-800">
                    <div className="flex justify-between items-start mb-3">
                      <div className="h-10 w-10 bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg flex items-center justify-center group-hover:bg-blue-100 dark:group-hover:bg-blue-900/50 transition-colors">
                        <FileText size={20} />
                      </div>
                      <span className="text-[10px] bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 px-2 py-0.5 rounded-full">Source</span>
                    </div>
                    <h3 className="font-medium text-neutral-900 dark:text-white truncate" title={source}>{source}</h3>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 line-clamp-2">
                      Source document retrieved from knowledge base.
                    </p>
                  </AgCard>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <AgCard className="p-4 border-neutral-200/60 dark:border-neutral-800 opacity-50">
                  <div className="flex justify-between items-start mb-3">
                    <div className="h-10 w-10 bg-neutral-100 dark:bg-neutral-800 rounded-lg flex items-center justify-center">
                      <BarChart3 size={20} className="text-neutral-400" />
                    </div>
                  </div>
                  <h3 className="font-medium text-neutral-900 dark:text-white">No Context</h3>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">Ask a question to retrieve documents.</p>
                </AgCard>
              </div>
            )}

            {/* Knowledge Base Results - UI Components */}
            {uiComponents.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between px-1">
                  <h2 className="text-sm font-semibold text-neutral-900 dark:text-white uppercase tracking-wider">Knowledge Base Results</h2>
                </div>
                {uiComponents.map((component: any, idx: number) => (
                  <ComponentRenderer key={idx} component={component} />
                ))}
              </div>
            )}

            {/* Retrieved Context Chunks */}
            {ragData?.chunks && ragData.chunks.length > 0 && (
              <div className="space-y-3 pt-4 border-t border-neutral-200 dark:border-neutral-800">
                <div className="flex items-center gap-2 mb-2">
                  <div className="h-6 w-6 rounded bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
                    <Database size={14} />
                  </div>
                  <h2 className="text-sm font-semibold text-neutral-900 dark:text-white uppercase tracking-wider">Retrieved Context</h2>
                  <span className="text-xs text-neutral-400 dark:text-neutral-500 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded-full">RAG Pipeline</span>
                </div>

                {(ragData.retrievalMeta?.retrieval_id || ragData.retrievalMeta?.trace_id) && (
                  <div className="flex flex-wrap items-center gap-2 mb-2 px-1">
                    {ragData.retrievalMeta?.retrieval_id && (
                      <span className="text-[11px] text-neutral-500 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded-full font-mono">
                        Retrieval: {ragData.retrievalMeta.retrieval_id}
                      </span>
                    )}
                    {ragData.retrievalMeta?.trace_id && (
                      <span className="text-[11px] text-neutral-500 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded-full font-mono">
                        Trace: {ragData.retrievalMeta.trace_id}
                      </span>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-1 gap-3">
                  {ragData.chunks.map((chunk: Chunk, idx: number) => {
                    const pageNumbers =
                      chunk.page_numbers ||
                      chunk.citation?.page_numbers ||
                      chunk.metadata?.page_numbers ||
                      (chunk.metadata?.page_no ? [chunk.metadata.page_no] : []);
                    const chunkId = chunk.citation?.chunk_id || chunk.id;

                    return (
                      <AgCard key={idx} className="p-4 bg-slate-50 dark:bg-neutral-800 border-indigo-100/50 dark:border-indigo-900/30 hover:border-indigo-200 dark:hover:border-indigo-800 transition-colors">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <AgBadge variant="default">Score: {chunk.similarity.toFixed(2)}</AgBadge>
                            <span className="text-xs font-mono text-neutral-500 dark:text-neutral-400">{chunk.filename}</span>
                            {pageNumbers.length > 0 && (
                              <span className="text-[11px] text-neutral-500 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-900 px-2 py-0.5 rounded-full">
                                Page{pageNumbers.length > 1 ? 's' : ''}: {pageNumbers.join(', ')}
                              </span>
                            )}
                          </div>
                          <ExternalLink size={14} className="text-neutral-400 hover:text-indigo-600 dark:hover:text-indigo-400 cursor-pointer" />
                        </div>
                        {chunkId && (
                          <div className="text-[11px] font-mono text-neutral-500 dark:text-neutral-400 mb-2">
                            Chunk: {chunkId}
                          </div>
                        )}
                        <p className="text-xs text-neutral-600 dark:text-neutral-300 font-mono leading-relaxed bg-white dark:bg-neutral-900 p-2 rounded border border-neutral-100 dark:border-neutral-700">
                          {chunk.content}
                        </p>
                      </AgCard>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
};
