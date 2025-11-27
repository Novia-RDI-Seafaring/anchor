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
      <div className="flex-1 flex flex-col items-center justify-center text-neutral-800 dark:text-neutral-200 p-6 animate-in fade-in duration-500">
        <div className="bg-neutral-100 dark:bg-neutral-800 p-3 rounded-full mb-4">
           <Sparkles className="h-5 w-5 text-neutral-600 dark:text-neutral-400" />
        </div>
        <h1 className="text-lg font-medium tracking-tight text-center mb-2">How can I help?</h1>
        <p className="text-xs text-neutral-400 text-center max-w-[200px]">
          Ask me to analyze data, generate reports, or search your knowledge base.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6 scroll-smooth">
      {messages.map((msg) => (
        <div 
          key={msg.id} 
          className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          {msg.role === 'assistant' && (
            <div className="w-6 h-6 rounded-full bg-teal-600 dark:bg-teal-500 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm text-white">
              <Bot size={14} />
            </div>
          )}
          
          <div className={`
            relative px-4 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm max-w-[90%]
            ${msg.role === 'user' 
              ? 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 rounded-tr-sm' 
              : 'bg-white border border-neutral-200 text-neutral-800 dark:bg-neutral-800 dark:border-neutral-700 dark:text-neutral-100 rounded-tl-sm'}
          `}>
             <div className="whitespace-pre-wrap">{msg.content}</div>
          </div>

          {msg.role === 'user' && (
            <div className="w-6 h-6 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center flex-shrink-0 mt-0.5">
              <User size={14} className="text-neutral-500 dark:text-neutral-400" />
            </div>
          )}
        </div>
      ))}
      <div className="h-2" /> {/* Spacer at bottom */}
    </div>
  );
};