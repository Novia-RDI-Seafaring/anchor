import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  ArrowLeft,
  Database,
  Check,
  FileText,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Trash2,
  Upload,
} from 'lucide-react';
import { AgCard, AgInput } from '../ui/AgComponents';
import { API_URL } from '@/lib/api-config';

interface Document {
  id: number;
  document_id: string;
  filename: string;
  source_type: string;
  status: string;
  chunk_count: number;
  created_at: string;
}

interface KBStats {
  total_documents: number;
  processed_documents: number;
  rag_vector_rows: number;
  rag_indexstore_rows: number;
  rag_docstore_rows: number;
  rag_schema: string;
  rag_vector_table: string;
  rag_indexstore_table: string;
  rag_docstore_table: string;
  status: string;
}

interface SettingsPageProps {
  onBack: () => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ onBack }) => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [stats, setStats] = useState<KBStats | null>(null);
  const [urlInput, setUrlInput] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchData = useCallback(async () => {
    try {
      const [docsRes, statsRes] = await Promise.all([
        fetch(`${API_URL}/api/documents`),
        fetch(`${API_URL}/api/stats`),
      ]);

      if (docsRes.ok) {
        const docsData = await docsRes.json();
        setDocuments(docsData.documents || []);
      }

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
    } catch (err) {
      console.error('Failed to fetch settings data:', err);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!error && !success) {
      return;
    }

    const timer = setTimeout(() => {
      setError(null);
      setSuccess(null);
    }, 5000);

    return () => clearTimeout(timer);
  }, [error, success]);

  const handleFileUpload = async () => {
    if (!selectedFile) return;

    setIsLoading(true);
    setLoadingAction('upload');
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);

      const res = await fetch(`${API_URL}/api/documents/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Upload failed');

      setSuccess(`Uploaded and processed: ${selectedFile.name}`);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsLoading(false);
      setLoadingAction(null);
    }
  };

  const handleAddUrl = async () => {
    if (!urlInput.trim()) return;

    setIsLoading(true);
    setLoadingAction('url');
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/documents/url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlInput }),
      });

      if (!res.ok) throw new Error('Failed to add URL');

      setSuccess('URL added to the knowledge base');
      setUrlInput('');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add URL');
    } finally {
      setIsLoading(false);
      setLoadingAction(null);
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/documents/${documentId}`, {
        method: 'DELETE',
      });

      if (!res.ok) throw new Error('Delete failed');

      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReingest = async () => {
    if (!confirm('This will re-process all documents. Continue?')) return;

    setIsLoading(true);
    setLoadingAction('reingest');
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/documents/reingest`, {
        method: 'POST',
      });

      if (!res.ok) throw new Error('Reingest failed');

      const data = await res.json();
      setSuccess(`Reingested ${data.processed ?? 0} documents`);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reingest failed');
    } finally {
      setIsLoading(false);
      setLoadingAction(null);
    }
  };

  const handleReset = async () => {
    if (!confirm('This will delete all registered documents, retrieval rows, and uploaded files. Continue?')) return;

    setIsLoading(true);
    setLoadingAction('reset');
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/documents/reset`, {
        method: 'DELETE',
      });

      if (!res.ok) throw new Error('Reset failed');

      const data = await res.json();
      setSuccess(
        `Deleted ${data.documents_deleted ?? 0} documents and ${data.rag_vectors_deleted ?? 0} KETJU rows`
      );
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setIsLoading(false);
      setLoadingAction(null);
    }
  };
  return (
    <div className="flex-1 h-full bg-neutral-50/50 dark:bg-neutral-950 overflow-y-auto p-4 md:p-8 animate-in fade-in slide-in-from-bottom-4 duration-300">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button
            onClick={onBack}
            className="p-2 hover:bg-neutral-200 dark:hover:bg-neutral-800 rounded-full text-neutral-600 dark:text-neutral-400 transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="flex items-center gap-2 text-xl font-bold text-neutral-900 dark:text-white">
            <Database className="h-6 w-6" />
            <h1>Knowledge Base</h1>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2 text-red-700 dark:text-red-400">
            <AlertTriangle size={16} />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
            <Check size={16} />
            <span className="text-sm">{success}</span>
          </div>
        )}

        <div className="space-y-6">
          <AgCard className="p-6 border-neutral-200 dark:border-neutral-800 shadow-sm">
              <div className="flex items-center gap-2 mb-6">
                <div className="h-8 w-8 rounded-lg bg-orange-50 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 flex items-center justify-center">
                  <Database size={18} />
                </div>
                <h2 className="text-lg font-bold text-neutral-900 dark:text-white">Knowledge Base</h2>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-6">
                <div className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-4">
                      <div className="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400 mb-1">Documents</div>
                      <div className="text-2xl font-semibold text-neutral-900 dark:text-white">{stats?.total_documents ?? 0}</div>
                      <div className="text-xs text-neutral-500 mt-1">{stats?.processed_documents ?? 0} processed</div>
                    </div>
                    <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-4">
                      <div className="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400 mb-1">KETJU Rows</div>
                      <div className="text-2xl font-semibold text-neutral-900 dark:text-white">{stats?.rag_vector_rows ?? 0}</div>
                      <div className="text-xs text-neutral-500 mt-1">{stats?.rag_indexstore_rows ?? 0} index rows</div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-4 space-y-2 text-sm">
                    <div className="font-semibold text-neutral-900 dark:text-white">Current storage layout</div>
                    <div className="text-neutral-600 dark:text-neutral-400">Registry table: <span className="font-mono">anchor.documents</span></div>
                    <div className="text-neutral-600 dark:text-neutral-400">
                      Retrieval table: <span className="font-mono">{stats?.rag_schema ?? 'public'}.{stats?.rag_vector_table ?? 'data_ketju_vectors'}</span>
                    </div>
                    <div className="text-neutral-600 dark:text-neutral-400">
                      Index table: <span className="font-mono">{stats?.rag_schema ?? 'public'}.{stats?.rag_indexstore_table ?? 'data_ketju_vectors_indexstore'}</span>
                    </div>
                    <div className="text-neutral-600 dark:text-neutral-400">
                      Docstore: <span className="font-mono">{stats?.rag_docstore_rows ? `${stats.rag_schema}.${stats.rag_docstore_table}` : 'not used in this flow'}</span>
                    </div>
                  </div>

                  <div className="bg-neutral-50 dark:bg-neutral-800/50 p-4 rounded-lg border border-neutral-100 dark:border-neutral-800">
                    <label className="block text-sm font-bold text-neutral-900 dark:text-white mb-3">Add URL</label>
                    <div className="space-y-3">
                      <AgInput
                        placeholder="https://example.com/file.pdf"
                        value={urlInput}
                        onChange={(e) => setUrlInput(e.target.value)}
                      />
                      <button
                        onClick={handleAddUrl}
                        disabled={isLoading || !urlInput.trim()}
                        className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors w-full md:w-auto flex items-center justify-center gap-2"
                      >
                        {loadingAction === 'url' && <Loader2 size={14} className="animate-spin" />}
                        Add URL
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">Document Upload</label>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.docx,.txt,.md,.html"
                      onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                      className="hidden"
                    />
                    <div className="flex gap-2">
                      <div className="flex rounded-md shadow-sm flex-1">
                        <button
                          onClick={() => fileInputRef.current?.click()}
                          className="relative inline-flex items-center rounded-l-md bg-neutral-800 dark:bg-neutral-700 px-3 py-2 text-sm font-semibold text-white hover:bg-neutral-700 dark:hover:bg-neutral-600 focus:z-10"
                        >
                          Choose File
                        </button>
                        <div className="relative -ml-px flex w-full items-center rounded-r-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-500 truncate">
                          {selectedFile?.name || 'No file chosen'}
                        </div>
                      </div>
                      {selectedFile && (
                        <button
                          onClick={handleFileUpload}
                          disabled={isLoading}
                          className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 text-white rounded-md text-sm font-medium flex items-center gap-1"
                        >
                          {loadingAction === 'upload' ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                          Upload
                        </button>
                      )}
                    </div>
                    <p className="text-xs text-neutral-500 mt-2">
                      Upload settings were removed here because they were not wired into the live Docling ingestion path.
                    </p>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300">Documents ({documents.length})</label>
                      <button
                        onClick={fetchData}
                        className="flex items-center gap-2 px-3 py-1.5 border border-neutral-300 dark:border-neutral-700 rounded text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800"
                      >
                        <RefreshCw size={14} />
                        Refresh
                      </button>
                    </div>
                    <div className="border border-neutral-200 dark:border-neutral-700 rounded-md p-2 bg-white dark:bg-neutral-900 max-h-72 overflow-y-auto">
                      {documents.length === 0 ? (
                        <div className="text-sm text-neutral-400 text-center py-4">No documents yet</div>
                      ) : (
                        <div className="space-y-1">
                          {documents.map((doc) => (
                            <div
                              key={doc.document_id}
                              className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm text-neutral-700 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-800 rounded group"
                            >
                              <div className="flex items-center gap-2 truncate">
                                <FileText size={14} className="text-neutral-400 flex-shrink-0" />
                                <span className="truncate">{doc.filename}</span>
                                <span className="text-xs text-neutral-400">({doc.chunk_count} nodes)</span>
                              </div>
                              <button
                                onClick={() => handleDeleteDocument(doc.document_id)}
                                className="opacity-0 group-hover:opacity-100 p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-opacity"
                                title="Delete document"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="border border-red-200 dark:border-red-900/50 rounded-lg p-4 bg-red-50/10 dark:bg-red-900/10 space-y-4">
                    <div className="text-sm font-bold text-red-600 dark:text-red-400">Maintenance</div>

                    <div className="space-y-2">
                      <div className="text-sm font-medium text-neutral-900 dark:text-white">Reingest all documents</div>
                      <div className="text-xs text-neutral-500">Rebuilds the KETJU retrieval rows from the registered documents.</div>
                      <button
                        onClick={handleReingest}
                        disabled={isLoading || documents.length === 0}
                        className="w-full px-3 py-2 border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 rounded text-sm font-medium hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                      >
                        {loadingAction === 'reingest' && <Loader2 size={12} className="animate-spin" />}
                        Reingest
                      </button>
                    </div>

                    <div className="h-px bg-red-100 dark:bg-red-900/30 w-full" />

                    <div className="space-y-2">
                      <div className="text-sm font-medium text-neutral-900 dark:text-white">Reset knowledge base</div>
                      <div className="text-xs text-neutral-500">Deletes the registry rows, KETJU rows, and uploaded files on disk.</div>
                      <button
                        onClick={handleReset}
                        disabled={isLoading}
                        className="w-full px-3 py-2 border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 rounded text-sm font-medium hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                      >
                        {loadingAction === 'reset' && <Loader2 size={12} className="animate-spin" />}
                        Reset
                      </button>
                    </div>
                  </div>
                </div>
              </div>
          </AgCard>
        </div>
      </div>
    </div>
  );
};
