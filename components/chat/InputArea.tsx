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
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
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
    <div className="w-full max-w-4xl mx-auto px-4 pb-6">
      
      {/* RAG / Context Controls Toolbar (Visual Only) */}
      <div className="flex items-center gap-2 mb-2 px-1">
        <button 
          onClick={() => setIsRagEnabled(!isRagEnabled)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${isRagEnabled ? 'bg-indigo-50 text-indigo-700 border border-indigo-200' : 'bg-neutral-100 text-neutral-500 border border-neutral-200'}`}
        >
          <Database size={12} />
          {isRagEnabled ? 'Context Active' : 'Context Off'}
        </button>
        <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-white border border-neutral-200 text-neutral-600 hover:bg-neutral-50">
          <Globe size={12} />
          <span>Web Search</span>
        </button>
      </div>

      <div className="relative group rounded-3xl bg-white shadow-sm border border-neutral-200 focus-within:ring-2 focus-within:ring-brand-500/20 focus-within:border-brand-500 transition-all duration-200">
        
        {/* Text Input */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter your message..."
          rows={1}
          disabled={disabled}
          className="w-full max-h-[200px] py-4 pl-4 pr-12 bg-transparent border-none resize-none focus:ring-0 text-neutral-800 placeholder:text-neutral-400 text-base"
          style={{ minHeight: '56px' }}
        />

        {/* Action Buttons */}
        <div className="absolute bottom-2 right-2 flex items-center gap-2">
          {text.length === 0 && (
             <button className="p-2 text-neutral-400 hover:text-neutral-600 transition-colors rounded-full hover:bg-neutral-100">
               <Paperclip size={20} />
             </button>
          )}
          <button 
            onClick={handleSend}
            disabled={!text.trim() || disabled}
            className={`
              h-10 w-10 flex items-center justify-center rounded-full transition-all duration-200
              ${text.trim() ? 'bg-black text-white hover:scale-105 hover:bg-neutral-800' : 'bg-neutral-200 text-neutral-400 cursor-not-allowed'}
            `}
          >
            <ArrowUp size={20} strokeWidth={2.5} />
          </button>
        </div>
      </div>
      
      <div className="mt-3 text-center">
        <p className="text-[11px] text-neutral-400">
          I can make mistakes. Remember to double-check important information.
        </p>
      </div>
    </div>
  );
};
