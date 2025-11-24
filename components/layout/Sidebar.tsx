import React from 'react';
import { 
  Anchor, 
  Plus, 
  Settings, 
  MessageSquare, 
  PanelLeftClose, 
  PanelLeftOpen 
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
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  toggleSidebar,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onSettingsClick
}) => {
  
  if (!isOpen) {
    return (
      <div className="hidden md:flex flex-col items-center py-4 w-16 border-r border-neutral-200 h-screen bg-neutral-50/50">
        <button onClick={toggleSidebar} className="p-2 hover:bg-neutral-200 rounded-md text-neutral-600 mb-4">
          <PanelLeftOpen size={20} />
        </button>
        <button onClick={onNewChat} className="p-2 hover:bg-neutral-200 rounded-md text-neutral-600" title="New Chat">
          <Plus size={20} />
        </button>
      </div>
    );
  }

  return (
    <div className={`
      fixed md:relative z-20 h-full w-64 flex-shrink-0 flex flex-col 
      bg-neutral-50/30 border-r border-neutral-200 
      transition-transform duration-300 ease-in-out
      ${isOpen ? 'translate-x-0' : '-translate-x-full md:hidden'}
    `}>
      {/* Header Logo Area */}
      <div className="flex items-center justify-between p-4 h-16">
        <div className="flex items-center gap-2 font-bold text-lg text-neutral-900">
          <Anchor className="h-6 w-6" />
          <span>ANCHOR</span>
        </div>
        <button onClick={toggleSidebar} className="md:hidden p-1 text-neutral-500">
          <PanelLeftClose size={18} />
        </button>
        <button onClick={toggleSidebar} className="hidden md:block p-1 text-neutral-400 hover:text-neutral-600">
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
      <div className="h-px bg-neutral-200 mx-4 mb-4" />

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto px-3 pb-4">
        <div className="flex items-center justify-between px-2 mb-2">
           <h3 className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">Conversations</h3>
           <button className="text-neutral-400 hover:text-neutral-600">
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
                  ? 'bg-brand-50 text-brand-900 shadow-sm border border-brand-100' 
                  : 'text-neutral-700 hover:bg-neutral-100 border border-transparent'}
              `}
            >
              <div className="font-medium text-sm truncate">{conv.title}</div>
              <div className={`text-xs mt-0.5 truncate ${activeConversationId === conv.id ? 'text-brand-600/70' : 'text-neutral-400'}`}>
                {conv.preview}
              </div>
            </button>
          ))}
        </div>
      </div>
      
      {/* Sidebar Footer (User Profile or Version could go here) */}
      <div className="p-4 border-t border-neutral-200 text-xs text-neutral-400 text-center">
        v1.0.4 · AG-UI
      </div>
    </div>
  );
};