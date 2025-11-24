import React from 'react';
import { Message } from '../../types';
import { Bot, User, Sparkles } from 'lucide-react';

interface ChatAreaProps {
  messages: Message[];
  isEmpty: boolean;
}

export const ChatArea: React.FC<ChatAreaProps> = ({ messages, isEmpty }) => {
  if (isEmpty) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-neutral-800 animate-in fade-in duration-500">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-neutral-100 p-3 rounded-full">
             <Sparkles className="h-6 w-6 text-neutral-600" />
          </div>
          <h1 className="text-2xl font-medium tracking-tight">What can I help you with?</h1>
        </div>
        
        {/* Suggested prompts could go here */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl w-full px-8 mt-4 opacity-60">
            {/* Placeholders for visual balance */}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-8 scroll-smooth">
      {messages.map((msg) => (
        <div 
          key={msg.id} 
          className={`flex gap-4 max-w-4xl mx-auto ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          {msg.role === 'assistant' && (
            <div className="w-8 h-8 rounded-full bg-teal-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-sm text-white">
              <Bot size={16} />
            </div>
          )}
          
          <div className={`
            relative px-5 py-3.5 rounded-2xl text-sm leading-relaxed shadow-sm max-w-[85%] md:max-w-[75%]
            ${msg.role === 'user' 
              ? 'bg-neutral-900 text-white rounded-tr-sm' 
              : 'bg-white border border-neutral-200 text-neutral-800 rounded-tl-sm'}
          `}>
             <div className="whitespace-pre-wrap">{msg.content}</div>
          </div>

          {msg.role === 'user' && (
            <div className="w-8 h-8 rounded-full bg-neutral-200 flex items-center justify-center flex-shrink-0 mt-1">
              <User size={16} className="text-neutral-500" />
            </div>
          )}
        </div>
      ))}
      <div className="h-4" /> {/* Spacer at bottom */}
    </div>
  );
};
