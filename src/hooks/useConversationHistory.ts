import { useState, useEffect, useCallback, useRef } from 'react';
import { Conversation } from '@/types';
import { API_URL } from '@/lib/api-config';

const CONVERSATIONS_URL = `${API_URL}/api/conversations`;

export const useConversationHistory = () => {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [isInitialized, setIsInitialized] = useState(false);
    const pendingUpdates = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

    // Load from DB on mount
    useEffect(() => {
        if (isInitialized) return;

        fetch(CONVERSATIONS_URL)
            .then(r => r.ok ? r.json() : [])
            .then((rows: any[]) => {
                if (rows.length > 0) {
                    const convs: Conversation[] = rows.map(r => ({
                        id: r.id,
                        title: r.title,
                        lastMessageAt: r.updated_at,
                        preview: `${r.message_count ?? 0} messages`,
                        messages: [],
                    }));
                    setConversations(convs);
                    setActiveId(convs[0].id);
                } else {
                    _createInDB(crypto.randomUUID(), 'New Conversation').then(conv => {
                        if (conv) {
                            setConversations([conv]);
                            setActiveId(conv.id);
                        }
                    });
                }
                setIsInitialized(true);
            })
            .catch(() => setIsInitialized(true));
    }, [isInitialized]);

    const _createInDB = async (id: string, title: string): Promise<Conversation | null> => {
        try {
            const r = await fetch(CONVERSATIONS_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, title }),
            });
            if (!r.ok) return null;
            const row = await r.json();
            return { id: row.id, title: row.title, lastMessageAt: row.updated_at, preview: '0 messages', messages: [] };
        } catch {
            return null;
        }
    };

    const createNewConversation = useCallback(async (): Promise<string> => {
        const id = crypto.randomUUID();
        const conv: Conversation = {
            id,
            title: 'New Conversation',
            lastMessageAt: 'Just now',
            preview: '0 messages',
            messages: [],
        };
        // Optimistic update
        setConversations(prev => [conv, ...prev]);
        setActiveId(id);
        // Persist
        await _createInDB(id, 'New Conversation');
        return id;
    }, []);

    const deleteConversation = useCallback((id: string) => {
        setConversations(prev => {
            const next = prev.filter(c => c.id !== id);
            if (activeId === id) {
                if (next.length > 0) {
                    setActiveId(next[0].id);
                } else {
                    // Create a fresh one if list becomes empty
                    const newId = crypto.randomUUID();
                    const newConv: Conversation = { id: newId, title: 'New Conversation', lastMessageAt: 'Just now', preview: '0 messages', messages: [] };
                    _createInDB(newId, 'New Conversation');
                    setActiveId(newId);
                    return [newConv];
                }
            }
            return next;
        });
        fetch(`${CONVERSATIONS_URL}/${id}`, { method: 'DELETE' }).catch(() => {});
    }, [activeId]);

    const updateConversation = useCallback((id: string, updates: Partial<Conversation>) => {
        setConversations(prev => prev.map(c => c.id === id ? { ...c, ...updates } : c));

        // Debounce DB write per conversation
        const existing = pendingUpdates.current.get(id);
        if (existing) clearTimeout(existing);

        const timer = setTimeout(() => {
            pendingUpdates.current.delete(id);
            const body: Record<string, any> = {};
            if (updates.title !== undefined) body.title = updates.title;
            if (updates.messages !== undefined) body.messages = updates.messages;
            if ((updates as any).canvas_state !== undefined) body.canvas_state = (updates as any).canvas_state;

            fetch(`${CONVERSATIONS_URL}/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            }).catch(() => {});
        }, 800);

        pendingUpdates.current.set(id, timer);
    }, []);

    const loadConversationMessages = useCallback(async (id: string): Promise<{ messages: any[]; canvas_state: any }> => {
        try {
            const r = await fetch(`${CONVERSATIONS_URL}/${id}`);
            if (!r.ok) return { messages: [], canvas_state: {} };
            const data = await r.json();
            return { messages: data.messages ?? [], canvas_state: data.canvas_state ?? {} };
        } catch {
            return { messages: [], canvas_state: {} };
        }
    }, []);

    return {
        conversations,
        activeId,
        setActiveId,
        createNewConversation,
        deleteConversation,
        updateConversation,
        loadConversationMessages,
    };
};
