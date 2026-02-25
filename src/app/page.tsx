"use client";

import React, { useCallback } from 'react';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { MainContent } from '@/components/layout/MainContent';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { DatabaseStatus } from '@/types';
import { Menu, MessageCircle } from 'lucide-react';
import { useApp } from '@/contexts/AppContext';
import { CopilotKit } from "@copilotkit/react-core";
import { ModelOption } from '@/types';

// Use environment variable or default to localhost:8001
const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8001';

export default function Home() {
    // Global state from Context
    const {
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
        activeConversationId,
        setActiveConversationId,
        conversations
    } = useApp();

    // Models state
    const [models, setModels] = React.useState<ModelOption[]>([]);

    // Fetch models on mount
    React.useEffect(() => {
        const fetchModels = async () => {
            try {
                const res = await fetch(`${API_URL}/api/models`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.models && data.models.length > 0) {
                        setModels(data.models);
                        // If current selected model is not in list, select first one
                        const currentExists = data.models.some((m: ModelOption) => m.id === selectedModel);
                        if (!currentExists && data.models.length > 0) {
                            setSelectedModel(data.models[0].id);
                        }
                    }
                }
            } catch (err) {
                console.error('Failed to fetch models:', err);
                // Fallback to default models happens automatically via initial state
            }
        };

        fetchModels();
    }, [selectedModel, setSelectedModel]);

    const handleNewChat = useCallback(() => {
        setCurrentView('workspace');
        setActiveConversationId('1');
        if (window.innerWidth < 768) setSidebarOpen(false);
    }, [setCurrentView, setActiveConversationId, setSidebarOpen]);

    const handleSelectConversation = useCallback((id: string) => {
        setCurrentView('workspace');
        setActiveConversationId(id);
        if (window.innerWidth < 768) setSidebarOpen(false);
    }, [setCurrentView, setActiveConversationId, setSidebarOpen]);

    const handleSettingsClick = useCallback(() => {
        setCurrentView('settings');
        setIsChatOpen(false);
        if (window.innerWidth < 768) setSidebarOpen(false);
    }, [setCurrentView, setIsChatOpen, setSidebarOpen]);

    const dbStatus: DatabaseStatus = {
        id: 'db-err',
        status: 'error',
        label: 'Error loading DBs'
    };

    const currentConversation = conversations.find(c => c.id === activeConversationId);

    return (
        <div className="flex h-screen w-full bg-white dark:bg-neutral-950 overflow-hidden text-neutral-900 dark:text-neutral-50 font-sans relative">

            {/* Left Sidebar (Navigation) */}
            <Sidebar
                isOpen={sidebarOpen}
                toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
                onSettingsClick={handleSettingsClick}
            />

            {/* Main App Container */}
            <div className="flex-1 flex flex-col h-full relative min-w-0 bg-white dark:bg-neutral-950">

                {/* Mobile Header Toggle */}
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
                        {/* Global Header */}
                        <Header
                            sidebarOpen={sidebarOpen}
                            toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
                            selectedModel={selectedModel}
                            onModelChange={setSelectedModel}
                            dbStatus={dbStatus}
                            models={models}
                        />

                        {/* Split View Content Area */}
                        <CopilotKit
                            runtimeUrl={`/api/copilotkit?model=${selectedModel}`}
                            agent="my_agent"
                            key={activeConversationId}
                            showDevConsole={false}  // DISABLE DEV CONSOLE FOR THE COPILOTKIT
                        >
                            <div className="flex-1 flex overflow-hidden relative">

                                {/* Center: Main Content / Artifacts */}
                                <div className="flex-1 flex flex-col min-w-0 bg-neutral-50/50 dark:bg-neutral-950">
                                    <MainContent />
                                </div>

                                {/* Right: Chat Interface (Minimizable) */}
                                <ChatInterface
                                    key={activeConversationId}
                                    isOpen={isChatOpen}
                                    onClose={() => setIsChatOpen(false)}
                                    initialMessages={currentConversation?.messages || []}
                                />

                                {/* Floating Chat Toggle (Visible when chat is closed) */}
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

