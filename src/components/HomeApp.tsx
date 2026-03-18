"use client";

import React, { useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { MainContent } from '@/components/layout/MainContent';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { Menu, MessageCircle } from 'lucide-react';
import { useApp } from '@/contexts/AppContext';
import { CopilotKit } from "@copilotkit/react-core";
import { ModelOption } from '@/types';
import { API_URL } from '@/lib/api-config';
import { normalizeModelOptions } from '@/lib/models';
import { ConversationRestorer } from '@/components/chat/ConversationRestorer';

interface HomeAppProps {
    initialThreadId?: string;
}

export function HomeApp({ initialThreadId }: HomeAppProps) {
    const router = useRouter();
    const {
        currentView,
        setCurrentView,
        sidebarOpen,
        setSidebarOpen,
        isChatOpen,
        setIsChatOpen,
        selectedModel,
        setSelectedModel,
        activeConversationId,
        setActiveConversationId,
        createNewConversation,
    } = useApp();

    // Apply initial thread from URL on mount
    useEffect(() => {
        if (initialThreadId) {
            setActiveConversationId(initialThreadId);
        }
    }, [initialThreadId]);

    // Keep URL in sync with active conversation
    useEffect(() => {
        if (activeConversationId) {
            router.replace(`/c/${activeConversationId}`);
        }
    }, [activeConversationId]);

    const [models, setModels] = React.useState<ModelOption[]>([]);

    React.useEffect(() => {
        const fetchModels = async () => {
            try {
                const res = await fetch(`${API_URL}/api/models`);
                if (res.ok) {
                    const data = await res.json();
                    const normalizedModels = normalizeModelOptions(data.models);
                    if (normalizedModels.length > 0) {
                        setModels(normalizedModels);
                        const currentExists = normalizedModels.some((m) => m.id === selectedModel);
                        if (!currentExists && normalizedModels[0]) {
                            setSelectedModel(normalizedModels[0].id);
                        }
                    }
                }
            } catch {
                // backend offline — suppress to avoid dev overlay noise
            }
        };
        fetchModels();
    }, [selectedModel, setSelectedModel]);

    const handleNewChat = useCallback(async () => {
        const conversationId = await createNewConversation();
        setCurrentView('workspace');
        setActiveConversationId(conversationId);
        setIsChatOpen(true);
        if (window.innerWidth < 768) setSidebarOpen(false);
    }, [createNewConversation, setCurrentView, setActiveConversationId, setIsChatOpen, setSidebarOpen]);

    const handleSelectConversation = useCallback((id: string) => {
        setCurrentView('workspace');
        setActiveConversationId(id);
        setIsChatOpen(true);
        if (window.innerWidth < 768) setSidebarOpen(false);
    }, [setCurrentView, setActiveConversationId, setIsChatOpen, setSidebarOpen]);

    const handleSettingsClick = useCallback(() => {
        setCurrentView('settings');
        setIsChatOpen(false);
        if (window.innerWidth < 768) setSidebarOpen(false);
    }, [setCurrentView, setIsChatOpen, setSidebarOpen]);

    return (
        <div className="flex h-screen w-full bg-white dark:bg-neutral-950 overflow-hidden text-neutral-900 dark:text-neutral-50 font-sans relative">

            <Sidebar
                isOpen={sidebarOpen}
                toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
                onSettingsClick={handleSettingsClick}
                onNewChat={handleNewChat}
                onConversationSelect={handleSelectConversation}
            />

            <div className="flex-1 flex flex-col h-full relative min-w-0 bg-white dark:bg-neutral-950">

                {!sidebarOpen && (
                    <button
                        onClick={() => setSidebarOpen(true)}
                        className="md:hidden absolute top-4 left-4 z-50 p-2 bg-white dark:bg-neutral-900 shadow-md rounded-md border border-neutral-100 dark:border-neutral-800 text-neutral-600 dark:text-neutral-400"
                    >
                        <Menu size={20} />
                    </button>
                )}

                {currentView === 'workspace' ? (
                    <>
                        <Header
                            selectedModel={selectedModel}
                            onModelChange={setSelectedModel}
                            models={models}
                        />

                        <CopilotKit
                            runtimeUrl={`/api/copilotkit?model=${selectedModel}`}
                            agent="my_agent"
                            threadId={activeConversationId}
                        >
                            <ConversationRestorer />
                            <div className="flex-1 flex overflow-hidden relative">

                                <div className="flex-1 flex flex-col min-w-0 bg-neutral-50/50 dark:bg-neutral-950">
                                    <MainContent />
                                </div>

                                <ChatInterface
                                    isOpen={isChatOpen}
                                    onClose={() => setIsChatOpen(false)}
                                />

                                {!isChatOpen && (
                                    <button
                                        onClick={() => setIsChatOpen(true)}
                                        className="absolute bottom-6 right-6 h-14 w-14 bg-black dark:bg-neutral-100 text-white dark:text-neutral-900 rounded-full shadow-lg hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-all hover:scale-105 flex items-center justify-center z-30"
                                        title="Open Chat"
                                    >
                                        <MessageCircle size={28} />
                                    </button>
                                )}
                            </div>
                        </CopilotKit>
                    </>
                ) : (
                    <SettingsPage onBack={() => {
                        setCurrentView('workspace');
                        setIsChatOpen(true);
                    }} />
                )}

            </div>
        </div>
    );
}
