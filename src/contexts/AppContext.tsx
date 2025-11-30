"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

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
    activeConversationId: string;
    setActiveConversationId: (id: string) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider = ({ children }: { children: ReactNode }) => {
    const [currentView, setCurrentView] = useState<'workspace' | 'settings'>('workspace');
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [isChatOpen, setIsChatOpen] = useState(true);
    const [isDarkMode, setIsDarkMode] = useState(false);
    const [selectedModel, setSelectedModel] = useState('llama3.2');
    const [activeConversationId, setActiveConversationId] = useState('1');

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
            activeConversationId,
            setActiveConversationId,
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
