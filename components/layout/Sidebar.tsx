import React from 'react';
import { 
  Anchor, 
  Plus, 
  Settings, 
  MessageSquare, 
  PanelLeftClose, 
  PanelLeftOpen,
  Moon,
  Sun
} from 'lucide-react';
import { AgButton } from '../ui/AgComponents';
import { Conversation } from '../../types';

interface SidebarProps {
  isOpen: boolean;
  toggleSidebar: () => void;
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onSettingsClick: () => void;
  isDarkMode: boolean;
  toggleDarkMode: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  toggleSidebar,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onSettingsClick,
  isDarkMode,
  toggleDarkMode
}) => {
  
  if (!isOpen) {
    return (
      <div className="hidden md:flex flex-col items-center py-4 w-16 border-r border-neutral-200 dark:border-neutral-800 h-screen bg-neutral-50/50 dark:bg-neutral-900/50">
        <button onClick={toggleSidebar} className="p-2 hover:bg-neutral-200 dark:hover:bg-neutral-800 rounded-md text-neutral-600 dark:text-neutral-400 mb-4">
          <PanelLeftOpen size={20} />
        </button>
        <button onClick={onNewChat} className="p-2 hover:bg-neutral-200 dark:hover:bg-neutral-800 rounded-md text-neutral-600 dark:text-neutral-400" title="New Chat">
          <Plus size={20} />
        </button>
      </div>
    );
  }

  return (
    <div className={`
      fixed md:relative z-20 h-full w-64 flex-shrink-0 flex flex-col 
      bg-neutral-50/30 dark:bg-neutral-900 border-r border-neutral-200 dark:border-neutral-800
      transition-transform duration-300 ease-in-out
      ${isOpen ? 'translate-x-0' : '-translate-x-full md:hidden'}
    `}>
      {/* Header Logo Area */}
      <div className="flex items-center justify-between p-4 h-16">
        <div className="flex items-center gap-2 font-bold text-lg text-neutral-900 dark:text-white">
          <Anchor className="h-6 w-6" />
          <span>ANCHOR</span>
        </div>
        <button onClick={toggleSidebar} className="md:hidden p-1 text-neutral-500 dark:text-neutral-400">
          <PanelLeftClose size={18} />
        </button>
        <button onClick={toggleSidebar} className="hidden md:block p-1 text-neutral-400 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300">
          <PanelLeftClose size={18} />
        </button>
      </div>

      {/* Primary Actions */}
      <div className="px-3 pb-4">
        <AgButton variant="ghost" className="w-full justify-start gap-3 mb-1" onClick={onNewChat}>
          <Plus size={18} />
          <span>New Chat</span>
        </AgButton>
        <AgButton variant="ghost" className="w-full justify-start gap-3" onClick={onSettingsClick}>
          <Settings size={18} />
          <span>Settings</span>
        </AgButton>
      </div>

      {/* Divider */}
      <div className="h-px bg-neutral-200 dark:bg-neutral-800 mx-4 mb-4" />

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto px-3 pb-4">
        <div className="flex items-center justify-between px-2 mb-2">
           <h3 className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">Conversations</h3>
           <button className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300">
             <MessageSquare size={14} />
           </button>
        </div>
       
        <div className="space-y-1">
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => onSelectConversation(conv.id)}
              className={`
                w-full text-left px-3 py-3 rounded-lg transition-colors group
                ${activeConversationId === conv.id 
                  ? 'bg-brand-50 dark:bg-brand-900/20 text-brand-900 dark:text-brand-100 shadow-sm border border-brand-100 dark:border-brand-900' 
                  : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-transparent'}
              `}
            >
              <div className="font-medium text-sm truncate">{conv.title}</div>
              <div className={`text-xs mt-0.5 truncate ${activeConversationId === conv.id ? 'text-brand-600/70 dark:text-brand-300/70' : 'text-neutral-400 dark:text-neutral-500'}`}>
                {conv.preview}
              </div>
            </button>
          ))}
        </div>
      </div>
      
      {/* Sidebar Footer */}
      <div className="p-4 border-t border-neutral-200 dark:border-neutral-800">
        <button 
          onClick={toggleDarkMode}
          className="flex items-center justify-between w-full px-3 py-2 text-sm text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-md transition-colors mb-2"
        >
          <span className="flex items-center gap-2">
            {isDarkMode ? <Moon size={16} /> : <Sun size={16} />}
            {isDarkMode ? 'Dark Mode' : 'Light Mode'}
          </span>
          <div className={`w-8 h-4 rounded-full relative transition-colors ${isDarkMode ? 'bg-indigo-600' : 'bg-neutral-300'}`}>
            <div className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform ${isDarkMode ? 'translate-x-4' : 'translate-x-0'}`} />
          </div>
        </button>
        <div className="text-xs text-neutral-400 dark:text-neutral-600 text-center mt-2">
          v1.0.4 · AG-UI
        </div>
      </div>
    </div>
  );
};