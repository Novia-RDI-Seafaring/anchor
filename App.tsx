import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { ChatArea } from './components/chat/ChatArea';
import { InputArea } from './components/chat/InputArea';
import { MainContent } from './components/layout/MainContent';
import { SettingsPage } from './components/settings/SettingsPage';
import { Conversation, Message, ModelOption, DatabaseStatus } from './types';
import { Menu, MessageCircle, X } from 'lucide-react';

// --- Mock Data ---
const MOCK_CONVERSATIONS: Conversation[] = [
  { id: '1', title: 'New Conversation', lastMessageAt: 'Just now', preview: '0 messages · Just now' },
  { id: '2', title: 'React Component Design', lastMessageAt: '2h ago', preview: '4 messages · 2h ago' },
  { id: '3', title: 'Project Anchor Analysis', lastMessageAt: '1d ago', preview: '12 messages · 1d ago' },
];

const MOCK_MODELS: ModelOption[] = [
  { id: 'llama3.2', label: 'LlamaStack - ollama/llama3.2:3b', provider: 'Ollama' },
  { id: 'gpt-4o', label: 'OpenAI - GPT-4o', provider: 'OpenAI' },
  { id: 'gemini-pro', label: 'Google - Gemini Pro', provider: 'Google' },
];

const MOCK_MESSAGES: Record<string, Message[]> = {
  '1': [],
  '2': [
    { id: 'm1', role: 'user', content: 'How do I center a div?', timestamp: new Date() },
    { id: 'm2', role: 'assistant', content: 'You can use Flexbox:\n\n```css\n.parent {\n  display: flex;\n  justify-content: center;\n  align-items: center;\n}\n```', timestamp: new Date() }
  ]
};

const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<'workspace' | 'settings'>('workspace');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [activeConversationId, setActiveConversationId] = useState<string>('1');
  const [selectedModel, setSelectedModel] = useState<string>('llama3.2');
  const [isDarkMode, setIsDarkMode] = useState(false);
  
  const [messages, setMessages] = useState<Message[]>([]);

  // Dark mode effect
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  React.useEffect(() => {
    const loadedMessages = MOCK_MESSAGES[activeConversationId] || [];
    setMessages(loadedMessages);
  }, [activeConversationId]);

  const handleSendMessage = (text: string) => {
    const newMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, newMessage]);

    setTimeout(() => {
      const response: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `I've received your query regarding "${text}". \n\nI'm updating the center dashboard with relevant data.`,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, response]);
    }, 1000);
  };

  const handleNewChat = () => {
    setCurrentView('workspace');
    setActiveConversationId('1');
    setMessages([]);
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

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
        onSelectConversation={(id) => {
          setCurrentView('workspace');
          setActiveConversationId(id);
          if (window.innerWidth < 768) setSidebarOpen(false);
        }}
        onNewChat={handleNewChat}
        onSettingsClick={() => {
          setCurrentView('settings');
          setIsChatOpen(false);
          if (window.innerWidth < 768) setSidebarOpen(false);
        }}
        isDarkMode={isDarkMode}
        toggleDarkMode={() => setIsDarkMode(!isDarkMode)}
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
              {isChatOpen && (
                <div className="w-full md:w-[400px] lg:w-[450px] flex flex-col bg-white dark:bg-neutral-900 border-l border-neutral-200 dark:border-neutral-800 shadow-xl z-20 absolute md:relative right-0 h-full animate-in slide-in-from-right duration-300">
                  
                  {/* Chat Header for Close Button */}
                  <div className="h-12 border-b border-neutral-100 dark:border-neutral-800 flex items-center justify-between px-4 bg-white/50 dark:bg-neutral-900/50 backdrop-blur-sm">
                    <span className="text-sm font-medium text-neutral-600 dark:text-neutral-400">Assistant</span>
                    <button 
                      onClick={() => setIsChatOpen(false)}
                      className="p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                      title="Minimize chat"
                    >
                      <X size={18} />
                    </button>
                  </div>

                  <ChatArea 
                    messages={messages} 
                    isEmpty={messages.length === 0} 
                  />
                  
                  <div className="flex-shrink-0 bg-white dark:bg-neutral-900 pt-2 border-t border-neutral-100 dark:border-neutral-800">
                    <InputArea onSendMessage={handleSendMessage} />
                  </div>
                </div>
              )}

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
};

export default App;