"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useConversationHistory } from '@/hooks/useConversationHistory';
import { Conversation } from '@/types';
import { API_URL } from '@/lib/api-config';

export interface KBDocument {
    document_id: string;
    filename: string;
    node_count: number;
    status?: string;
}

export interface FocusedChatNode {
    nodeId: string;
    nodeType: string;
    title: string;
    summary: string;
    filename?: string;
    page?: number;
    bbox?: number[];
}

const MAX_FOCUSED_CHAT_NODES = 2;

interface AppContextType {
    currentView: 'workspace' | 'settings';
    setCurrentView: (view: 'workspace' | 'settings') => void;
    sidebarOpen: boolean;
    setSidebarOpen: (open: boolean) => void;
    isChatOpen: boolean;
    setIsChatOpen: (open: boolean) => void;
    isDarkMode: boolean;
    toggleDarkMode: () => void;
    selectedModel: string;
    setSelectedModel: (model: string) => void;
    activeDocumentId: string | null;
    setActiveDocumentId: (id: string | null) => void;
    focusedChatNodes: FocusedChatNode[];
    addFocusedChatNode: (node: FocusedChatNode) => void;
    removeFocusedChatNode: (nodeId: string) => void;
    clearFocusedChatNodes: () => void;
    documents: KBDocument[];
    refreshDocuments: () => Promise<void>;
    activeConversationId: string;
    setActiveConversationId: (id: string) => void;
    conversations: Conversation[];
    createNewConversation: () => Promise<string>;
    deleteConversation: (id: string) => void;
    updateConversation: (id: string, updates: Partial<Conversation>) => void;
    loadConversationMessages: (id: string) => Promise<{ messages: any[]; canvas_state: any }>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider = ({ children }: { children: ReactNode }) => {
    const [currentView, setCurrentView] = useState<'workspace' | 'settings'>('workspace');
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [isChatOpen, setIsChatOpen] = useState(true);
    const [isDarkMode, setIsDarkMode] = useState(false);
    const [selectedModel, setSelectedModel] = useState('');
    const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
    const [focusedChatNodes, setFocusedChatNodes] = useState<FocusedChatNode[]>([]);
    const [documents, setDocuments] = useState<KBDocument[]>([]);

    const addFocusedChatNode = (node: FocusedChatNode) => {
        setFocusedChatNodes((prev) => {
            const withoutExisting = prev.filter((item) => item.nodeId !== node.nodeId);
            const next = [...withoutExisting, node];
            return next.slice(-MAX_FOCUSED_CHAT_NODES);
        });
    };

    const removeFocusedChatNode = (nodeId: string) => {
        setFocusedChatNodes((prev) => prev.filter((item) => item.nodeId !== nodeId));
    };

    const clearFocusedChatNodes = () => {
        setFocusedChatNodes([]);
    };

    const refreshDocuments = async () => {
        try {
            const r = await fetch(`${API_URL}/api/documents`);
            if (r.ok) {
                const data = await r.json();
                if (data) setDocuments(data.documents || []);
            }
        } catch { /* ignore */ }
    };

    useEffect(() => {
        refreshDocuments();
        const interval = setInterval(refreshDocuments, 30000);
        return () => clearInterval(interval);
    }, []);

    const {
        conversations,
        activeId: activeConversationId,
        setActiveId: setActiveConversationId,
        createNewConversation,
        deleteConversation,
        updateConversation,
        loadConversationMessages,
    } = useConversationHistory();

    const toggleDarkMode = () => setIsDarkMode((prev: boolean) => !prev);

    // Dark mode effect
    useEffect(() => {
        document.documentElement.classList.toggle('dark', isDarkMode);
    }, [isDarkMode]);

    return (
        <AppContext.Provider value={{
            currentView,
            setCurrentView,
            sidebarOpen,
            setSidebarOpen,
            isChatOpen,
            setIsChatOpen,
            isDarkMode,
            toggleDarkMode,
            selectedModel,
            setSelectedModel,
            activeDocumentId,
            setActiveDocumentId,
            focusedChatNodes,
            addFocusedChatNode,
            removeFocusedChatNode,
            clearFocusedChatNodes,
            documents,
            refreshDocuments,
            activeConversationId: activeConversationId || '',
            setActiveConversationId,
            conversations,
            createNewConversation,
            deleteConversation,
            updateConversation,
            loadConversationMessages,
        }}>
            {children}
        </AppContext.Provider>
    );
};

export const useApp = () => {
    const context = useContext(AppContext);
    if (!context) {
        throw new Error('useApp must be used within AppProvider');
    }
    return context;
};
