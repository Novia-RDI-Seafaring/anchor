import { useState, useEffect, useCallback } from 'react';
import { Conversation } from '@/types';
import { Message } from "@copilotkit/runtime-client-gql";

const STORAGE_KEY = 'anchor_conversations';

export const useConversationHistory = () => {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [isInitialized, setIsInitialized] = useState(false);

    // Load from local storage on mount - ONCE ONLY
    useEffect(() => {
        if (isInitialized) return;

        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
            try {
                const parsed = JSON.parse(stored);
                setConversations(parsed);
                if (parsed.length > 0) {
                    setActiveId(parsed[0].id);
                }
            } catch (e) {
                console.error("Failed to parse conversations", e);
                // Create default conversation on parse error
                const defaultConv: Conversation = {
                    id: crypto.randomUUID(),
                    title: 'New Conversation',
                    lastMessageAt: 'Just now',
                    preview: '0 messages - Just now',
                    messages: []
                };
                setConversations([defaultConv]);
                setActiveId(defaultConv.id);
            }
        } else {
            // No stored data - create initial conversation
            const initialConv: Conversation = {
                id: crypto.randomUUID(),
                title: 'New Conversation',
                lastMessageAt: 'Just now',
                preview: '0 messages - Just now',
                messages: []
            };
            setConversations([initialConv]);
            setActiveId(initialConv.id);
        }

        setIsInitialized(true);
    }, [isInitialized]);

    // Save to local storage with debounce for performance
    useEffect(() => {
        if (!isInitialized || conversations.length === 0) return;

        const timeoutId = setTimeout(() => {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
        }, 300); // Debounce 300ms

        return () => clearTimeout(timeoutId);
    }, [conversations, isInitialized]);

    const createNewConversation = useCallback(() => {
        const newConv: Conversation = {
            id: crypto.randomUUID(),
            title: 'New Conversation',
            lastMessageAt: 'Just now',
            preview: '0 messages - Just now',
            messages: []
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
                    preview: '0 messages - Just now',
                    messages: []
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
