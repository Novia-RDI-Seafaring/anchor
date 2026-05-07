import { useState, useEffect, useCallback, useRef } from 'react';
import { useSession } from 'next-auth/react';
import { Conversation } from '@/types';
import { API_URL } from '@/lib/api-config';

const CONVERSATIONS_URL = `${API_URL}/api/conversations`;

export const useConversationHistory = () => {
    const { data: session, status } = useSession();
    // TODO(remove after development): keep local conversations working when auth is bypassed.
    // Only fall back to the dev user once the session has actually resolved — otherwise the
    // first render (status === 'loading') briefly fetches the dev user's threads before the
    // real session arrives, flashing "not logged in" state in the sidebar.
    const sessionReady = status !== 'loading';
    const userId: string | null = sessionReady ? ((session?.user as any)?.id ?? 'local-dev-user') : null;
    const userHeaders: Record<string, string> = userId ? { 'x-user-id': userId } : {};

    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [isInitialized, setIsInitialized] = useState(false);
    const pendingUpdates = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
    const pendingCreates = useRef<Map<string, Promise<Conversation | null>>>(new Map());

    // Reset and reload when user changes
    const prevUserId = useRef<string | null>(null);
    useEffect(() => {
        if (!userId) return;
        if (userId === prevUserId.current) return;
        prevUserId.current = userId;
        setIsInitialized(false);
        setConversations([]);
        setActiveId(null);
    }, [userId]);

    // Load from DB on mount (or when user changes)
    useEffect(() => {
        if (isInitialized || !userId) return;

        fetch(CONVERSATIONS_URL, { headers: userHeaders })
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
                    setActiveId(convs[0]?.id ?? null);
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
    }, [isInitialized, userId]);

    const _createInDB = async (id: string, title: string): Promise<Conversation | null> => {
        try {
            const r = await fetch(CONVERSATIONS_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...userHeaders },
                body: JSON.stringify({ id, title }),
            });
            if (!r.ok) return null;
            const row = await r.json();
            return { id: row.id, title: row.title, lastMessageAt: row.updated_at, preview: '0 messages', messages: [] };
        } catch {
            return null;
        }
    };

    const ensureConversationExists = useCallback(async (id: string, title = 'New Conversation'): Promise<boolean> => {
        if (pendingCreates.current.has(id)) {
            const existing = await pendingCreates.current.get(id)!;
            return existing !== null;
        }

        const createPromise = _createInDB(id, title)
            .finally(() => {
                pendingCreates.current.delete(id);
            });

        pendingCreates.current.set(id, createPromise);
        const created = await createPromise;
        return created !== null;
    }, []);

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
        await ensureConversationExists(id, 'New Conversation');
        return id;
    }, [ensureConversationExists]);

    const deleteConversation = useCallback((id: string) => {
        const pending = pendingUpdates.current.get(id);
        if (pending) {
            clearTimeout(pending);
            pendingUpdates.current.delete(id);
        }

        setConversations(prev => {
            const next = prev.filter(c => c.id !== id);
            if (activeId === id) {
                if (next.length > 0) {
                    setActiveId(next[0]?.id ?? null);
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
        fetch(`${CONVERSATIONS_URL}/${id}`, { method: 'DELETE', headers: userHeaders }).catch(() => {});
    }, [activeId]);

    const updateConversation = useCallback((id: string, updates: Partial<Conversation>) => {
        setConversations(prev => prev.map(c => c.id === id ? { ...c, ...updates } : c));

        // Debounce DB write per conversation
        const existing = pendingUpdates.current.get(id);
        if (existing) clearTimeout(existing);

        const timer = setTimeout(async () => {
            pendingUpdates.current.delete(id);
            const body: Record<string, any> = {};
            if (updates.title !== undefined) body.title = updates.title;
            if (updates.messages !== undefined) body.messages = updates.messages;
            if ((updates as any).canvas_state !== undefined) body.canvas_state = (updates as any).canvas_state;

            try {
                let response = await fetch(`${CONVERSATIONS_URL}/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', ...userHeaders },
                    body: JSON.stringify(body),
                });

                if (response.status === 404) {
                    const conversation = conversations.find(c => c.id === id);
                    const title = body.title ?? conversation?.title ?? 'New Conversation';
                    const created = await ensureConversationExists(id, title);
                    if (!created) return;

                    response = await fetch(`${CONVERSATIONS_URL}/${id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json', ...userHeaders },
                        body: JSON.stringify(body),
                    });
                }
            } catch {
                // swallow network issues; optimistic local state remains
            }
        }, 800);

        pendingUpdates.current.set(id, timer);
    }, [conversations, ensureConversationExists]);

    const loadConversationMessages = useCallback(async (id: string): Promise<{ messages: any[]; canvas_state: any }> => {
        try {
            let r = await fetch(`${CONVERSATIONS_URL}/${id}`, { headers: userHeaders });
            if (r.status === 404) {
                const conversation = conversations.find(c => c.id === id);
                const created = await ensureConversationExists(id, conversation?.title ?? 'New Conversation');
                if (!created) return { messages: [], canvas_state: {} };
                r = await fetch(`${CONVERSATIONS_URL}/${id}`, { headers: userHeaders });
            }
            if (!r.ok) return { messages: [], canvas_state: {} };
            const data = await r.json();
            return { messages: data.messages ?? [], canvas_state: data.canvas_state ?? {} };
        } catch {
            return { messages: [], canvas_state: {} };
        }
    }, [conversations, ensureConversationExists]);

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
