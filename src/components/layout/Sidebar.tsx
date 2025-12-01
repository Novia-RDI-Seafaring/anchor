import React, { useState } from 'react';
import {
  Anchor,
  Plus,
  Settings,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Moon,
  Sun,
  Trash2,
  Edit2,
  Check,
  X
} from 'lucide-react';
import { AgButton } from '../ui/AgComponents';
import { useApp } from '@/contexts/AppContext';

interface SidebarProps {
  isOpen: boolean;
  toggleSidebar: () => void;
  onSettingsClick: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  toggleSidebar,
  onSettingsClick,
}) => {
  const {
    conversations,
    activeConversationId,
    setActiveConversationId,
    createNewConversation,
    deleteConversation,
    updateConversation,
    isDarkMode,
    toggleDarkMode
  } = useApp();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const onNewChat = () => {
    createNewConversation();
  };

  const onSelectConversation = (id: string) => {
    setActiveConversationId(id);
  };

  const handleStartEdit = (id: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(id);
    setEditTitle(currentTitle);
  };

  const handleSaveEdit = (id: string, e?: React.MouseEvent | React.KeyboardEvent) => {
    e?.stopPropagation();
    if (editTitle.trim()) {
      updateConversation(id, { title: editTitle.trim() });
    }
    setEditingId(null);
    setEditTitle('');
  };

  const handleCancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
    setEditTitle('');
  };

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this conversation?')) {
      deleteConversation(id);
    }
  };

  const handleKeyDown = (id: string, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSaveEdit(id, e);
    } else if (e.key === 'Escape') {
      e.stopPropagation();
      setEditingId(null);
      setEditTitle('');
    }
  };

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
            <div
              key={conv.id}
              className={`
                w-full text-left px-3 py-2.5 rounded-lg transition-colors group relative
                ${activeConversationId === conv.id
                  ? 'bg-brand-50 dark:bg-brand-900/20 text-brand-900 dark:text-brand-100 shadow-sm border border-brand-100 dark:border-brand-900'
                  : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-transparent'}
              `}
            >
              {editingId === conv.id ? (
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => handleKeyDown(conv.id, e)}
                    autoFocus
                    className="flex-1 px-2 py-1 text-sm bg-white dark:bg-neutral-800 border border-brand-300 dark:border-brand-700 rounded focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                  <button
                    onClick={(e) => handleSaveEdit(conv.id, e)}
                    className="p-1 hover:bg-green-100 dark:hover:bg-green-900/30 rounded text-green-600 dark:text-green-400"
                    title="Save"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded text-red-600 dark:text-red-400"
                    title="Cancel"
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : (
                <div
                  onClick={() => onSelectConversation(conv.id)}
                  className="w-full text-left cursor-pointer"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm truncate">{conv.title}</div>
                      <div className={`text-xs mt-0.5 truncate ${activeConversationId === conv.id ? 'text-brand-600/70 dark:text-brand-300/70' : 'text-neutral-400 dark:text-neutral-500'}`}>
                        {conv.preview}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => handleStartEdit(conv.id, conv.title, e)}
                        className="p-1.5 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded text-blue-600 dark:text-blue-400"
                        title="Rename"
                      >
                        <Edit2 size={14} />
                      </button>
                      <button
                        onClick={(e) => handleDelete(conv.id, e)}
                        className="p-1.5 hover:bg-red-100 dark:hover:bg-red-900/30 rounded text-red-600 dark:text-red-400"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
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