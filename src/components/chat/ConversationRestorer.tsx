"use client";

import { useEffect, useRef } from 'react';
import { useCopilotChatInternal } from '@copilotkit/react-core';
import { useApp } from '@/contexts/AppContext';

/**
 * Restores stored messages from the DB into CopilotKit when a conversation
 * is loaded or switched. Must be rendered inside <CopilotKit>.
 */
export function ConversationRestorer() {
    const { activeConversationId, loadConversationMessages } = useApp();
    const chat = useCopilotChatInternal();
    const restoredForId = useRef<string | null>(null);

    useEffect(() => {
        if (!activeConversationId) return;
        if (restoredForId.current === activeConversationId) return;
        restoredForId.current = activeConversationId;

        loadConversationMessages(activeConversationId).then(({ messages }) => {
            if (!messages?.length) return;

            const restored = messages
                .filter((m: any) => m.role && m.content)
                .map((m: any) => ({ id: m.id, role: m.role, content: m.content }));

            if (restored.length > 0) {
                chat.setMessages(restored as any);
            }
        });
    }, [activeConversationId]);

    return null;
}
