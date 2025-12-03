import React, { useMemo } from 'react';
import { useApp } from '@/contexts/AppContext';
import { AgCard, AgButton, AgBadge } from '../ui/AgComponents';
import { BarChart3, Table, Image as ImageIcon, FileText, Download, MoreHorizontal, Share2, Database, ExternalLink } from 'lucide-react';
import { useCopilotChat } from "@copilotkit/react-core";
import { Message, TextMessage } from "@copilotkit/runtime-client-gql";

interface Chunk {
  content: string;
  filename: string;
  similarity: number;
  metadata: any;
}

interface ToolResult {
  chunks: Chunk[];
  sources: string[];
}

export const MainContent: React.FC = () => {
  const { visibleMessages } = useCopilotChat();
  const { activeConversationId, updateConversation, conversations } = useApp();

  // Persist messages and update title
  React.useEffect(() => {
    if (!activeConversationId || visibleMessages.length === 0) return;

    const currentConv = conversations.find(c => c.id === activeConversationId);
    if (!currentConv) return;

    // Only update if messages actually changed (avoid unnecessary updates)
    const currentMessages = currentConv.messages || [];
    if (currentMessages.length === visibleMessages.length) {
      // Simple check - could be improved with deep equality
      return;
    }

    const updates: any = {
      messages: visibleMessages.map(msg => {
        // Serialize messages properly for storage
        if (msg.isTextMessage()) {
          const textMsg = msg as TextMessage;
          return {
            id: msg.id,
            role: textMsg.role,
            content: textMsg.content,
            type: 'text'
          };
        }
        // For other message types, store as-is (they should be serializable)
        return msg;
      }),
      lastMessageAt: 'Just now',
      preview: `${visibleMessages.length} messages · Just now`
    };

    // Check if we need to update (simple check: length changed or last message different)
    // For now, just update on every change to visibleMessages. 
    // Optimization: could check deep equality or length.

    //const updates: any = {
    //  messages: visibleMessages,
    //  lastMessageAt: 'Just now',
    //  preview: `${visibleMessages.length} messages · Just now`
    //};

    // Auto-generate title if it's the first user message and title is default
    if (currentConv.title === 'New Conversation' && visibleMessages.length > 0) {
      const firstUserMsg = visibleMessages.find(m => m.isTextMessage() && m.role === 'user');
      if (firstUserMsg) {
        const content = (firstUserMsg as TextMessage).content;
        updates.title = content.length > 30 ? content.substring(0, 30) + '...' : content;
      }
    }

    updateConversation(activeConversationId, updates);

  }, [visibleMessages, activeConversationId, updateConversation, conversations]);
  // Note: 'conversations' is not in dependency array to avoid loop, but we access it inside.
  // Ideally we should use a ref or pass a callback to updateConversation that checks the current state.
  // But since updateConversation updates state, it will trigger re-render.
  // If visibleMessages is stable, this effect won't run.

  const { latestResponse, ragData } = useMemo(() => {
    let response: string | null = null;
    let data: ToolResult | null = null;

    // Iterate backwards to find the latest relevant messages
    for (let i = visibleMessages.length - 1; i >= 0; i--) {
      const msg = visibleMessages[i];

      if (!msg) continue;

      // Find latest assistant text response
      if (!response && msg.isTextMessage() && msg.role === 'assistant') {
        response = (msg as TextMessage).content;
      }

      // Find latest RAG tool output
      if (!data) {
        const toolMsg = msg as any; // Cast to access tool-specific props

        // Debug log to see what messages look like
        if (toolMsg.role === 'function' || toolMsg.type === 'function' || toolMsg.toolName || toolMsg.name) {
          console.log("Found potential tool message:", toolMsg);
        }

        // Check for various properties that might identify the tool
        const isRagTool =
          toolMsg.toolName === 'query_knowledge_base' ||
          toolMsg.name === 'query_knowledge_base' ||
          (toolMsg.actionName === 'query_knowledge_base'); // Some versions might use actionName

        if (isRagTool && (toolMsg.result || toolMsg.content)) {
          try {
            const contentToParse = toolMsg.result || toolMsg.content;
            console.log("Parsing RAG data from:", contentToParse);

            // Handle case where content might already be an object
            if (typeof contentToParse === 'object') {
              data = contentToParse;
            } else {
              data = JSON.parse(contentToParse);
            }
            console.log("Parsed RAG data:", data);
          } catch (e) {
            console.error("Failed to parse tool result", e);
          }
        }
      }

      if (response && data) break;
    }

    return { latestResponse: response, ragData: data };
  }, [visibleMessages]);

  return (
    <div className="flex-1 h-full bg-neutral-50/50 dark:bg-neutral-950 overflow-y-auto p-4 md:p-8 scroll-smooth border-r border-neutral-200 dark:border-neutral-800">
      <div className="max-w-5xl mx-auto space-y-8">

        {/* Header Section */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold text-neutral-900 dark:text-white mb-2">Project Workspace</h1>
            <p className="text-neutral-500 dark:text-neutral-400 text-sm md:text-base">Generated artifacts and retrieved documents appear here.</p>
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

        {/* Sources Grid (formerly Mock Cards) */}
        {ragData?.sources && ragData.sources.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {ragData.sources.map((source, idx) => (
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
            {/* Fallback/Empty State Placeholders */}
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

        {/* Active Document (Agent Response) */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-white uppercase tracking-wider">Active Document</h2>
          </div>

          <AgCard className="overflow-hidden bg-white dark:bg-neutral-900 shadow-sm ring-1 ring-black/5 dark:ring-white/5">
            <div className="border-b border-neutral-100 dark:border-neutral-800 bg-neutral-50/30 dark:bg-neutral-900/30 px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-brand-600 dark:text-brand-400" />
                <span className="text-sm font-medium text-neutral-700 dark:text-neutral-200">
                  {ragData?.sources?.[0] || 'Response'}
                </span>
              </div>
              <div className="flex gap-2">
                <AgButton variant="ghost" size="sm" className="h-8 w-8 p-0">
                  <Download size={16} />
                </AgButton>
                <AgButton variant="secondary" size="sm" className="text-xs h-8">Edit</AgButton>
              </div>
            </div>

            <div className="p-6 md:p-10 bg-white dark:bg-neutral-900 min-h-[500px] text-sm md:text-base">
              <div className="prose prose-neutral dark:prose-invert prose-sm md:prose-base max-w-none">
                {latestResponse ? (
                  <div dangerouslySetInnerHTML={{ __html: latestResponse.replace(/\n/g, '<br/>') }} />
                ) : (
                  <p className="text-neutral-500 italic">Waiting for agent response...</p>
                )}
              </div>
            </div>
          </AgCard>
        </div>

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

            <div className="grid grid-cols-1 gap-3">
              {ragData.chunks.map((chunk, idx) => (
                <AgCard key={idx} className="p-4 bg-slate-50 dark:bg-neutral-800 border-indigo-100/50 dark:border-indigo-900/30 hover:border-indigo-200 dark:hover:border-indigo-800 transition-colors">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <AgBadge variant="default">Score: {chunk.similarity.toFixed(2)}</AgBadge>
                      <span className="text-xs font-mono text-neutral-500 dark:text-neutral-400">{chunk.filename}</span>
                    </div>
                    <ExternalLink size={14} className="text-neutral-400 hover:text-indigo-600 dark:hover:text-indigo-400 cursor-pointer" />
                  </div>
                  <p className="text-xs text-neutral-600 dark:text-neutral-300 font-mono leading-relaxed bg-white dark:bg-neutral-900 p-2 rounded border border-neutral-100 dark:border-neutral-700">
                    {chunk.content}
                  </p>
                </AgCard>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
};