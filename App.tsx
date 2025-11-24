import React, { useState } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { ChatArea } from './components/chat/ChatArea';
import { InputArea } from './components/chat/InputArea';
import { Conversation, Message, ModelOption, DatabaseStatus } from './types';
import { Menu } from 'lucide-react';

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
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeConversationId, setActiveConversationId] = useState<string>('1');
  const [selectedModel, setSelectedModel] = useState<string>('llama3.2');
  
  // Local state for messages to allow adding new ones
  const [messages, setMessages] = useState<Message[]>([]);

  // Simulate loading messages when conversation changes
  React.useEffect(() => {
    // In a real app, this would be an API call
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

    // Mock assistant response
    setTimeout(() => {
      const response: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `I've received your query regarding "${text}". \n\nThis is a mock response from the RAG system simulating a retrieval step followed by generation.`,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, response]);
    }, 1000);
  };

  const handleNewChat = () => {
    // Logic to create new chat ID would go here
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
    <div className="flex h-screen w-full bg-white overflow-hidden text-neutral-900">
      
      {/* Left Sidebar */}
      <Sidebar 
        isOpen={sidebarOpen} 
        toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        conversations={MOCK_CONVERSATIONS}
        activeConversationId={activeConversationId}
        onSelectConversation={(id) => {
          setActiveConversationId(id);
          if (window.innerWidth < 768) setSidebarOpen(false);
        }}
        onNewChat={handleNewChat}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-full relative min-w-0 bg-white">
        
        {/* Mobile Header Toggle */}
        {!sidebarOpen && (
           <button 
             onClick={() => setSidebarOpen(true)}
             className="md:hidden absolute top-4 left-4 z-20 p-2 bg-white shadow-md rounded-md border border-neutral-100"
           >
             <Menu size={20} />
           </button>
        )}

        {/* Top Navigation Bar */}
        <Header 
          sidebarOpen={sidebarOpen}
          toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          dbStatus={dbStatus}
          models={MOCK_MODELS}
        />

        {/* Chat Scroll Area */}
        <ChatArea 
          messages={messages} 
          isEmpty={messages.length === 0} 
        />

        {/* Fixed Input Area */}
        <div className="flex-shrink-0 bg-gradient-to-t from-white via-white to-transparent pt-10">
          <InputArea onSendMessage={handleSendMessage} />
        </div>

      </div>
    </div>
  );
};

export default App;
