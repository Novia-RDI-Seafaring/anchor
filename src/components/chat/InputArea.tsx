import React, { useState, useRef, useEffect, memo, useCallback } from 'react';
import { ArrowUp, Paperclip, Database, Globe, X, Loader2, FileText } from 'lucide-react';
import { useApp } from '@/contexts/AppContext';
import { UploadOptionsModal, UploadOptions } from '../modals/UploadOptionsModal';

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8001';

interface InputAreaProps {
  onSendMessage: (text: string) => void;
  disabled?: boolean;
}

interface UploadingFile {
  file: File;
  status: 'uploading' | 'success' | 'error';
  error?: string;
}

const InputAreaComponent: React.FC<InputAreaProps> = ({ onSendMessage, disabled }) => {
  const [text, setText] = useState('');
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);
  const [showOptionsModal, setShowOptionsModal] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<FileList | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { isRagEnabled, setIsRagEnabled } = useApp();

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [text]);

  const handleSend = useCallback(() => {
    if (text.trim() && !disabled) {
      onSendMessage(text);
      setText('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    }
  }, [text, disabled, onSendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const toggleRag = useCallback(() => {
    setIsRagEnabled(!isRagEnabled);
  }, [setIsRagEnabled, isRagEnabled]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Store files and show options modal
    setPendingFiles(files);
    setShowOptionsModal(true);
  }, []);

  const handleUploadWithOptions = useCallback(async (options: UploadOptions) => {
    setShowOptionsModal(false);

    if (!pendingFiles) return;

    // Process each file with the selected options
    for (const file of Array.from(pendingFiles)) {
      // Add to uploading state
      setUploadingFiles(prev => [...prev, { file, status: 'uploading' }]);

      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('preserve_images', String(options.preserveImages));
        formData.append('preserve_tables', String(options.preserveTables));
        formData.append('enable_ocr', String(options.enableOcr));
        formData.append('table_mode', options.tableMode);

        const res = await fetch(`${API_URL}/api/documents/upload`, {
          method: 'POST',
          body: formData
        });

        if (!res.ok) throw new Error('Upload failed');

        // Update status to success
        setUploadingFiles(prev =>
          prev.map(f => f.file === file ? { ...f, status: 'success' } : f)
        );

        // Remove success notification after 3 seconds
        setTimeout(() => {
          setUploadingFiles(prev => prev.filter(f => f.file !== file));
        }, 3000);

      } catch (err) {
        // Update status to error
        setUploadingFiles(prev =>
          prev.map(f => f.file === file ? {
            ...f,
            status: 'error',
            error: err instanceof Error ? err.message : 'Upload failed'
          } : f)
        );

        // Remove error notification after 5 seconds
        setTimeout(() => {
          setUploadingFiles(prev => prev.filter(f => f.file !== file));
        }, 5000);
      }
    }

    // Clear pending files and reset input
    setPendingFiles(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [pendingFiles]);

  const removeUploadingFile = useCallback((file: File) => {
    setUploadingFiles(prev => prev.filter(f => f.file !== file));
  }, []);

  return (
    <div className="w-full px-4 pb-4">

      {/* Uploading Files Status */}
      {uploadingFiles.length > 0 && (
        <div className="mb-2 space-y-1">
          {uploadingFiles.map((upload, idx) => (
            <div
              key={`${upload.file.name}-${idx}`}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs ${upload.status === 'uploading'
                ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300'
                : upload.status === 'success'
                  ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                  : 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                }`}
            >
              {upload.status === 'uploading' ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <FileText size={12} />
              )}
              <span className="truncate flex-1">{upload.file.name}</span>
              {upload.status === 'uploading' && <span>Uploading...</span>}
              {upload.status === 'success' && <span>Added to KB</span>}
              {upload.status === 'error' && <span>{upload.error}</span>}
              <button
                onClick={() => removeUploadingFile(upload.file)}
                className="p-0.5 hover:bg-black/10 rounded"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* RAG / Context Controls Toolbar */}
      <div className="flex items-center gap-2 mb-2 px-1 overflow-x-auto no-scrollbar">
        <button
          onClick={toggleRag}
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

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.txt,.md,.html"
          multiple
          onChange={handleFileSelect}
          className="hidden"
        />

        {/* Text Input */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          rows={1}
          disabled={disabled}
          className="w-full max-h-[150px] py-3 pl-3 pr-20 bg-transparent border-none resize-none focus:ring-0 text-neutral-800 dark:text-neutral-200 placeholder:text-neutral-400 text-sm"
          style={{ minHeight: '44px' }}
        />

        {/* Action Buttons */}
        <div className="absolute bottom-1.5 right-1.5 flex items-center gap-1">
          {text.length === 0 && (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-1.5 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors rounded-full hover:bg-neutral-100 dark:hover:bg-neutral-800"
              title="Upload file to knowledge base"
            >
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

      {/* Upload Options Modal */}
      <UploadOptionsModal
        isOpen={showOptionsModal}
        files={pendingFiles}
        onClose={() => {
          setShowOptionsModal(false);
          setPendingFiles(null);
          if (fileInputRef.current) fileInputRef.current.value = '';
        }}
        onConfirm={handleUploadWithOptions}
      />
    </div>
  );
};

// Memoized export
export const InputArea = memo(InputAreaComponent);
InputArea.displayName = 'InputArea';
