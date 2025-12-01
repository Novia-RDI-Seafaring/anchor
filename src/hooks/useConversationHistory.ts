import { useState, useEffect, useCallback } from 'react';
import { Conversation } from '@/types';
import { Message } from "@copilotkit/runtime-client-gql";

const STORAGE_KEY = 'anchor_conversations';

export const useConversationHistory = () => {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [activeId, setActiveId] = useState<string | null>(null);

    // Load from local storage on mount
    useEffect(() => {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
            try {
                const parsed = JSON.parse(stored);
                setConversations(parsed);
                if (parsed.length > 0 && !activeId) {
                    setActiveId(parsed[0].id);
                }
            } catch (e) {
                console.error("Failed to parse conversations", e);
            }
        } else {
            // Initialize with a default conversation if empty
            createNewConversation();
        }
    }, []);

    // Save to local storage whenever conversations change
    useEffect(() => {
        if (conversations.length > 0) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
        }
    }, [conversations]);

    const createNewConversation = useCallback(() => {
        const newConv: Conversation = {
            id: crypto.randomUUID(),
            title: 'New Conversation',
            lastMessageAt: 'Just now',
            preview: '0 messages · Just now',
            messages: [] // We'll need to extend the type to include messages if we want to persist them fully here
        };

        setConversations(prev => [newConv, ...prev]);
        setActiveId(newConv.id);
        return newConv.id;
    }, []);

    const deleteConversation = useCallback((id: string) => {
        setConversations(prev => {
            const newConvs = prev.filter(c => c.id !== id);
            if (activeId === id && newConvs.length > 0) {
                setActiveId(newConvs[0]?.id ?? null);
            } else if (newConvs.length === 0) {
                // Always keep at least one
                const newConv = {
                    id: crypto.randomUUID(),
                    title: 'New Conversation',
                    lastMessageAt: 'Just now',
                    preview: '0 messages · Just now'
                };
                setActiveId(newConv.id);
                return [newConv];
            }
            return newConvs;
        });
    }, [activeId]);

    const updateConversation = useCallback((id: string, updates: Partial<Conversation>) => {
        setConversations(prev => prev.map(c => c.id === id ? { ...c, ...updates } : c));
    }, []);

    return {
        conversations,
        activeId,
        setActiveId,
        createNewConversation,
        deleteConversation,
        updateConversation
    };
};
