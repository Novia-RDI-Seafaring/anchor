import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Paperclip, Database, Globe } from 'lucide-react';

interface InputAreaProps {
  onSendMessage: (text: string) => void;
  disabled?: boolean;
}

export const InputArea: React.FC<InputAreaProps> = ({ onSendMessage, disabled }) => {
  const [text, setText] = useState('');
  const [isRagEnabled, setIsRagEnabled] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [text]);

  const handleSend = () => {
    if (text.trim() && !disabled) {
      onSendMessage(text);
      setText('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="w-full px-4 pb-4">
      
      {/* RAG / Context Controls Toolbar (Visual Only) */}
      <div className="flex items-center gap-2 mb-2 px-1 overflow-x-auto no-scrollbar">
        <button 
          onClick={() => setIsRagEnabled(!isRagEnabled)}
          className={`flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium transition-all ${isRagEnabled ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-300 dark:border-indigo-800' : 'bg-neutral-100 text-neutral-500 border border-neutral-200 dark:bg-neutral-800 dark:text-neutral-400 dark:border-neutral-700'}`}
        >
          <Database size={10} />
          {isRagEnabled ? 'Context On' : 'Context Off'}
        </button>
        <button className="flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700">
          <Globe size={10} />
          <span>Web</span>
        </button>
      </div>

      <div className="relative group rounded-2xl bg-white dark:bg-neutral-900 shadow-sm border border-neutral-200 dark:border-neutral-800 focus-within:ring-2 focus-within:ring-brand-500/20 focus-within:border-brand-500 transition-all duration-200">
        
        {/* Text Input */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          rows={1}
          disabled={disabled}
          className="w-full max-h-[150px] py-3 pl-3 pr-10 bg-transparent border-none resize-none focus:ring-0 text-neutral-800 dark:text-neutral-200 placeholder:text-neutral-400 text-sm"
          style={{ minHeight: '44px' }}
        />

        {/* Action Buttons */}
        <div className="absolute bottom-1.5 right-1.5 flex items-center gap-1">
          {text.length === 0 && (
             <button className="p-1.5 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors rounded-full hover:bg-neutral-100 dark:hover:bg-neutral-800">
               <Paperclip size={16} />
             </button>
          )}
          <button 
            onClick={handleSend}
            disabled={!text.trim() || disabled}
            className={`
              h-8 w-8 flex items-center justify-center rounded-full transition-all duration-200
              ${text.trim() ? 'bg-black dark:bg-white text-white dark:text-black hover:scale-105 hover:bg-neutral-800 dark:hover:bg-neutral-200' : 'bg-neutral-200 dark:bg-neutral-800 text-neutral-400 cursor-not-allowed'}
            `}
          >
            <ArrowUp size={16} strokeWidth={2.5} />
          </button>
        </div>
      </div>
      
      <div className="mt-2 text-center">
        <p className="text-[10px] text-neutral-400 truncate">
          AI checks are recommended.
        </p>
      </div>
    </div>
  );
};