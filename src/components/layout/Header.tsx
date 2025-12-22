import React, { useState, useEffect, useCallback } from 'react';
import { AgSelect, AgBadge } from '../ui/AgComponents';
import { Database, Cpu, FileText } from 'lucide-react';
import { DatabaseStatus, ModelOption } from '../../types';

// Use environment variable or default to localhost:8001
// Ensure we don't end up with 'undefined' string
const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8001';

interface Document {
  document_id: string;
  filename: string;
  chunk_count: number;
}

interface HeaderProps {
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  selectedModel: string;
  onModelChange: (id: string) => void;
  dbStatus: DatabaseStatus;
  models: ModelOption[];
}

export const Header: React.FC<HeaderProps> = ({
  selectedModel,
  onModelChange,
  dbStatus,
  models
}) => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>('all');

  // Fetch documents list
  useEffect(() => {
    let mounted = true;
    const fetchDocs = async () => {
      try {
        const res = await fetch(`${API_URL}/api/documents`);
        if (res.ok) {
          const data = await res.json();
          if (mounted) setDocuments(data.documents || []);
        }
      } catch (err) {
        // Silently fail or log debug only to avoid console spam during dev if backend is down
        console.warn('Failed to fetch documents (backend might be down):', err);
      }
    };

    fetchDocs();
    // Refresh every 30 seconds
    const interval = setInterval(fetchDocs, 30000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Handle document selection
  const handleDocSelect = useCallback(async (docId: string) => {
    setSelectedDocId(docId);
    try {
      await fetch(`${API_URL}/api/active-document?document_id=${docId === 'all' ? '' : docId}`, {
        method: 'POST'
      });
    } catch (err) {
      console.error('Failed to set active document:', err);
    }
  }, []);

  // Build document options for selector
  const docOptions = [
    { id: 'all', label: 'All Documents' },
    ...documents.map(doc => ({
      id: doc.document_id,
      label: `${doc.filename} (${doc.chunk_count} chunks)`
    }))
  ];

  return (
    <header className="h-16 border-b border-neutral-100 dark:border-neutral-800 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-sm flex items-center justify-between px-4 md:px-6 z-30 sticky top-0">

      {/* Left: Document Selector */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-neutral-500" />
          <AgSelect
            options={docOptions}
            value={selectedDocId}
            onChange={handleDocSelect}
            className="w-56"
            placeholder="Select Document"
          />
          {documents.length > 0 && (
            <span className="hidden md:inline-block text-xs text-neutral-400">
              {documents.length} doc{documents.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Right: Model Selector */}
      <div className="flex items-center gap-4">
        <div className="hidden md:flex items-center text-xs text-neutral-400 dark:text-neutral-500 gap-1 mr-2">
          <span>RAG Pipeline</span>
          <span className="w-px h-3 bg-neutral-300 dark:bg-neutral-700 mx-1"></span>
          <span className="text-green-600 dark:text-green-500 font-medium">Ready</span>
        </div>
        <AgSelect
          options={models.filter(m => m.type === 'chat' || !m.type)}
          value={selectedModel}
          onChange={onModelChange}
          align="right"
          className="min-w-[240px]"
          icon={<Cpu size={16} />}
        />
      </div>
    </header>
  );
};
