import React, { useState, useRef, useEffect, memo, useCallback } from 'react';
import { ArrowUp, Paperclip, X, Loader2, FileText, ChevronDown } from 'lucide-react';
import { API_URL } from '@/lib/api-config';
import { useApp } from '@/contexts/AppContext';

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
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const { documents, activeDocumentId, setActiveDocumentId, refreshDocuments } = useApp();
  const activeDoc = documents.find(d => d.document_id === activeDocumentId) ?? null;

  // Close picker on outside click
  useEffect(() => {
    if (!docPickerOpen) return;
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setDocPickerOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [docPickerOpen]);

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

  const uploadFiles = useCallback(async (files: File[]) => {
    for (const file of files) {
      // Add to uploading state
      setUploadingFiles(prev => [...prev, { file, status: 'uploading' }]);

      try {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch(`${API_URL}/api/documents/upload`, {
          method: 'POST',
          body: formData
        });

        if (!res.ok) throw new Error('Upload failed');

        // Update status to success and refresh document list
        setUploadingFiles(prev =>
          prev.map(f => f.file === file ? { ...f, status: 'success' } : f)
        );
        refreshDocuments();

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

    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    void uploadFiles(Array.from(files));
  }, [uploadFiles]);

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

      <div className="relative group rounded-2xl bg-white dark:bg-neutral-900 shadow-sm border border-neutral-200 dark:border-neutral-800 focus-within:ring-2 focus-within:ring-brand-500/20 focus-within:border-brand-500 transition-all duration-200">

        {/* Document scope selector */}
        <div className="px-3 pt-2.5 pb-0 flex items-center gap-1.5" ref={pickerRef}>
          <div className="relative inline-block">
            <button
              type="button"
              onClick={() => setDocPickerOpen(o => !o)}
              className={`flex items-center gap-1.5 text-xs rounded-full px-2.5 py-1 border transition-colors ${
                activeDoc
                  ? 'bg-indigo-50 dark:bg-indigo-900/30 border-indigo-200 dark:border-indigo-700 text-indigo-700 dark:text-indigo-300'
                  : 'bg-neutral-100 dark:bg-neutral-800 border-neutral-200 dark:border-neutral-700 text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
              }`}
            >
              <FileText size={11} />
              <span className="max-w-[160px] truncate">
                {activeDoc ? activeDoc.filename : 'All documents'}
              </span>
              {activeDoc ? (
                <span
                  role="button"
                  onClick={(e) => { e.stopPropagation(); setActiveDocumentId(null); }}
                  className="ml-0.5 hover:text-red-500 transition-colors"
                  title="Clear filter"
                >
                  <X size={10} />
                </span>
              ) : (
                <ChevronDown size={10} className={`transition-transform ${docPickerOpen ? 'rotate-180' : ''}`} />
              )}
            </button>

            {/* Dropdown */}
            {docPickerOpen && (
              <div className="absolute left-0 top-full mt-1 z-50 min-w-[220px] max-w-xs rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 shadow-lg py-1 text-xs">
                <button
                  className="w-full text-left px-3 py-2 hover:bg-neutral-50 dark:hover:bg-neutral-800 text-neutral-500 dark:text-neutral-400"
                  onClick={() => { setActiveDocumentId(null); setDocPickerOpen(false); }}
                >
                  All documents
                </button>
                {documents.length > 0 && <div className="border-t border-neutral-100 dark:border-neutral-800 my-1" />}
                {documents.map(doc => (
                  <button
                    key={doc.document_id}
                    className={`w-full text-left px-3 py-2 hover:bg-neutral-50 dark:hover:bg-neutral-800 truncate ${
                      doc.document_id === activeDocumentId
                        ? 'text-indigo-600 dark:text-indigo-400 font-medium'
                        : 'text-neutral-700 dark:text-neutral-300'
                    }`}
                    onClick={() => { setActiveDocumentId(doc.document_id); setDocPickerOpen(false); }}
                    title={doc.filename}
                  >
                    {doc.filename}
                  </button>
                ))}
                {documents.length === 0 && (
                  <p className="px-3 py-2 text-neutral-400">No documents in KB</p>
                )}
              </div>
            )}
          </div>

          {/* Upload button — sits next to the scope pill */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1 text-xs rounded-full px-2.5 py-1 border border-neutral-200 dark:border-neutral-700 bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
            title="Upload file to knowledge base"
          >
            <Paperclip size={11} />
            <span>Upload</span>
          </button>
        </div>

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
          className="w-full max-h-[150px] pt-2 pb-3 pl-3 pr-20 bg-transparent border-none resize-none focus:ring-0 text-neutral-800 dark:text-neutral-200 placeholder:text-neutral-400 text-sm"
          style={{ minHeight: '44px' }}
        />

        {/* Action Buttons */}
        <div className="absolute bottom-1.5 right-1.5 flex items-center gap-1">
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
          Ask for source-backed answers. Scope your question to a document or upload new ones.
        </p>
      </div>

    </div>
  );
};

// Memoized export
export const InputArea = memo(InputAreaComponent);
InputArea.displayName = 'InputArea';
