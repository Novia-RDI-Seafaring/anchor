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
import { MOCK_CONVERSATIONS, MOCK_MODELS } from '@/lib/mock-data';

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
    } = useApp();

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

    return (
        <div className="flex h-screen w-full bg-white dark:bg-neutral-950 overflow-hidden text-neutral-900 dark:text-neutral-50 font-sans relative">

            {/* Left Sidebar (Navigation) */}
            <Sidebar
                isOpen={sidebarOpen}
                toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
                conversations={MOCK_CONVERSATIONS}
                activeConversationId={activeConversationId}
                onSelectConversation={handleSelectConversation}
                onNewChat={handleNewChat}
                onSettingsClick={handleSettingsClick}
                isDarkMode={isDarkMode}
                toggleDarkMode={toggleDarkMode}
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
                            models={MOCK_MODELS}
                        />

                        {/* Split View Content Area */}
                        <div className="flex-1 flex overflow-hidden relative">

                            {/* Center: Main Content / Artifacts */}
                            <div className="flex-1 flex flex-col min-w-0 bg-neutral-50/50 dark:bg-neutral-950">
                                <MainContent />
                            </div>

                            {/* Right: Chat Interface (Minimizable) */}
                            <ChatInterface
                                isOpen={isChatOpen}
                                onClose={() => setIsChatOpen(false)}
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

