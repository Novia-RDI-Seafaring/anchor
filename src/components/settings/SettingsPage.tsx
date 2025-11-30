import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  ArrowLeft, 
  Bot, 
  Settings2, 
  Database, 
  Check, 
  X, 
  FileText, 
  HardDrive, 
  Globe, 
  Layout, 
  RefreshCw,
  AlertTriangle,
  Loader2,
  Trash2,
  Upload
} from 'lucide-react';
import { AgCard, AgInput, AgSelect, AgBadge, AgToggle } from '../ui/AgComponents';

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8001';

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
  total_chunks: number;
  status: string;
}

interface SettingsPageProps {
  onBack: () => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ onBack }) => {
  // State for form controls
  const [temperature, setTemperature] = useState('0.7');
  const [maxTokens, setMaxTokens] = useState('2048');
  const [mcpTools, setMcpTools] = useState({
    filesystem: false,
    webSearch: false,
    database: false,
    markitdown: false
  });

  // Knowledge base state
  const [documents, setDocuments] = useState<Document[]>([]);
  const [stats, setStats] = useState<KBStats | null>(null);
  const [urlInput, setUrlInput] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch documents and stats
  const fetchData = useCallback(async () => {
    try {
      const [docsRes, statsRes] = await Promise.all([
        fetch(`${API_URL}/api/documents`),
        fetch(`${API_URL}/api/stats`)
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
      console.error('Failed to fetch KB data:', err);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Clear messages after timeout
  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  // Upload file
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
        body: formData
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

  // Add URL
  const handleAddUrl = async () => {
    if (!urlInput.trim()) return;
    
    setIsLoading(true);
    setLoadingAction('url');
    setError(null);
    
    try {
      const res = await fetch(`${API_URL}/api/documents/url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlInput })
      });
      
      if (!res.ok) throw new Error('Failed to add URL');
      
      setSuccess('URL added to knowledge base');
      setUrlInput('');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add URL');
    } finally {
      setIsLoading(false);
      setLoadingAction(null);
    }
  };

  // Delete document
  const handleDeleteDocument = async (documentId: string) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const res = await fetch(`${API_URL}/api/documents/${documentId}`, {
        method: 'DELETE'
      });
      
      if (!res.ok) throw new Error('Delete failed');
      
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Reingest all
  const handleReingest = async () => {
    if (!confirm('This will re-process all documents. Continue?')) return;
    
    setIsLoading(true);
    setLoadingAction('reingest');
    setError(null);
    
    try {
      const res = await fetch(`${API_URL}/api/documents/reingest`, {
        method: 'POST'
      });
      
      if (!res.ok) throw new Error('Reingest failed');
      
      const data = await res.json();
      setSuccess(`Reingested ${data.processed} documents`);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reingest failed');
    } finally {
      setIsLoading(false);
      setLoadingAction(null);
    }
  };

  // Reset knowledge base
  const handleReset = async () => {
    if (!confirm('This will DELETE ALL documents and chunks. This cannot be undone. Continue?')) return;
    
    setIsLoading(true);
    setLoadingAction('reset');
    setError(null);
    
    try {
      const res = await fetch(`${API_URL}/api/documents/reset`, {
        method: 'DELETE'
      });
      
      if (!res.ok) throw new Error('Reset failed');
      
      const data = await res.json();
      setSuccess(`Deleted ${data.documents_deleted} documents and ${data.chunks_deleted} chunks`);
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
      <div className="max-w-7xl mx-auto">
        
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button 
            onClick={onBack}
            className="p-2 hover:bg-neutral-200 dark:hover:bg-neutral-800 rounded-full text-neutral-600 dark:text-neutral-400 transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="flex items-center gap-2 text-xl font-bold text-neutral-900 dark:text-white">
            <Settings2 className="h-6 w-6" />
            <h1>Settings</h1>
          </div>
        </div>

        {/* Status Messages */}
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

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          
          {/* Column 1: AI Assistant Configuration */}
          <div className="space-y-6">
            <AgCard className="p-6 border-neutral-200 dark:border-neutral-800 shadow-sm">
              <div className="flex items-center gap-2 mb-6">
                <div className="h-8 w-8 rounded-lg bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
                  <Bot size={20} />
                </div>
                <h2 className="text-lg font-bold text-neutral-900 dark:text-white">AI Assistant Configuration</h2>
              </div>

              <div className="space-y-6">
                
                {/* System Prompt */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Configuration</label>
                  <label className="block text-xs text-neutral-500 mb-1">System Prompt</label>
                  <textarea 
                    className="w-full h-24 rounded-md border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none resize-none dark:text-neutral-100"
                    defaultValue="You are a knowledgeable and helpful assistant. CRITICAL: You must ONLY use information from the provided documents to answer questions."
                  />
                  <p className="text-xs text-neutral-500 mt-1">This defines how your AI agent will behave and respond to questions.</p>
                </div>

                {/* Model Selection */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Model Selection</label>
                  <label className="block text-xs text-neutral-500 mb-1">Select AI Model</label>
                  <AgSelect 
                    options={[{ id: 'llama3.2', label: 'LlamaStack - ollama/llama3.2:3b' }]}
                    value="llama3.2"
                    onChange={() => {}}
                    className="w-full"
                  />
                  <div className="flex items-center gap-1.5 mt-2 text-xs text-emerald-600 dark:text-emerald-500">
                    <Check size={12} strokeWidth={3} />
                    <span>Found 4 available model(s)</span>
                  </div>
                </div>

                {/* Advanced Settings */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-4">Advanced Settings</label>
                  
                  <div className="space-y-4">
                    <AgInput 
                      label="Temperature"
                      value={temperature}
                      onChange={(e) => setTemperature(e.target.value)}
                      placeholder="0.7"
                    />
                    <p className="text-xs text-neutral-500 -mt-2">Controls randomness (0.0 = focused, 1.0 = creative)</p>

                    <AgInput 
                      label="Max Tokens"
                      value={maxTokens}
                      onChange={(e) => setMaxTokens(e.target.value)}
                      placeholder="2048"
                    />
                    <p className="text-xs text-neutral-500 -mt-2">Maximum response length</p>
                  </div>
                </div>

                {/* MCP Tools */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">MCP Tools</label>
                  <p className="text-xs text-neutral-500 mb-4">Select which MCP (Model Context Protocol) tools to enable for your agent:</p>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between py-2">
                       <div className="flex items-center gap-2">
                         <div className="h-5 w-5 rounded border border-neutral-300 dark:border-neutral-600"></div>
                         <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Enable MCP Tools</span>
                       </div>
                    </div>

                    <div className="space-y-2 bg-neutral-50 dark:bg-neutral-800/50 p-4 rounded-lg border border-neutral-100 dark:border-neutral-800">
                      <div className="flex items-center justify-between p-2 bg-white dark:bg-neutral-900 rounded border border-neutral-100 dark:border-neutral-800">
                        <div className="flex items-center gap-2">
                          <HardDrive size={16} className="text-purple-400" />
                          <div>
                            <div className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Filesystem</div>
                            <div className="text-[10px] text-neutral-400">Endpoint: http://localhost:8000/sse</div>
                          </div>
                        </div>
                        <AgToggle checked={mcpTools.filesystem} onChange={(c) => setMcpTools({...mcpTools, filesystem: c})} />
                      </div>

                      <div className="flex items-center justify-between p-2 bg-white dark:bg-neutral-900 rounded border border-neutral-100 dark:border-neutral-800">
                        <div className="flex items-center gap-2">
                          <Globe size={16} className="text-purple-400" />
                          <div>
                            <div className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Web_Search</div>
                            <div className="text-[10px] text-neutral-400">Endpoint: https://mcp.search-provider.com/sse</div>
                          </div>
                        </div>
                        <AgToggle checked={mcpTools.webSearch} onChange={(c) => setMcpTools({...mcpTools, webSearch: c})} />
                      </div>

                      <div className="flex items-center justify-between p-2 bg-white dark:bg-neutral-900 rounded border border-neutral-100 dark:border-neutral-800">
                        <div className="flex items-center gap-2">
                          <Database size={16} className="text-purple-400" />
                          <div>
                            <div className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Database</div>
                            <div className="text-[10px] text-neutral-400">Endpoint:</div>
                          </div>
                        </div>
                        <AgToggle checked={mcpTools.database} onChange={(c) => setMcpTools({...mcpTools, database: c})} />
                      </div>

                      <div className="flex items-center justify-between p-2 bg-white dark:bg-neutral-900 rounded border border-neutral-100 dark:border-neutral-800">
                        <div className="flex items-center gap-2">
                          <Layout size={16} className="text-purple-400" />
                          <div>
                            <div className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Markitdown</div>
                            <div className="text-[10px] text-neutral-400">Endpoint: http://localhost:8001/sse</div>
                          </div>
                        </div>
                        <AgToggle checked={mcpTools.markitdown} onChange={(c) => setMcpTools({...mcpTools, markitdown: c})} />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Status Section */}
                <div>
                   <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">Status</label>
                   <label className="block text-xs text-neutral-500 mb-2">Current Configuration</label>
                   
                   <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-lg p-4 space-y-2 text-sm border border-neutral-100 dark:border-neutral-800">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700 dark:text-neutral-300">System Prompt:</span>
                        <span className="text-emerald-600 dark:text-emerald-500">Configured</span>
                        <Check size={14} className="text-emerald-500" />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700 dark:text-neutral-300">Selected Model:</span>
                        <span className="text-emerald-600 dark:text-emerald-500">ollama/llama3.2:3b</span>
                        <Check size={14} className="text-emerald-500" />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700 dark:text-neutral-300">Temperature:</span>
                        <span className="text-neutral-600 dark:text-neutral-400">{temperature}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700 dark:text-neutral-300">Max Tokens:</span>
                        <span className="text-neutral-600 dark:text-neutral-400">{maxTokens}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700 dark:text-neutral-300">MCP Tools:</span>
                        <span className="text-red-500 dark:text-red-400">Disabled</span>
                        <X size={14} className="text-red-500 dark:text-red-400" />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700 dark:text-neutral-300">Knowledge Base:</span>
                        {stats?.status === 'connected' ? (
                          <>
                            <span className="text-emerald-600 dark:text-emerald-500">
                              {stats.total_documents} docs, {stats.total_chunks} chunks
                            </span>
                            <Check size={14} className="text-emerald-500" />
                          </>
                        ) : (
                          <>
                            <span className="text-amber-600 dark:text-amber-500">Connecting...</span>
                            <Loader2 size={14} className="text-amber-500 animate-spin" />
                          </>
                        )}
                      </div>
                   </div>
                </div>

              </div>
            </AgCard>
          </div>

          {/* Column 2: Knowledge Base Management */}
          <div className="space-y-6">
            <AgCard className="p-6 border-neutral-200 dark:border-neutral-800 shadow-sm">
              <div className="flex items-center gap-2 mb-6">
                <div className="h-8 w-8 rounded-lg bg-orange-50 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 flex items-center justify-center">
                  <Database size={20} />
                </div>
                <h2 className="text-lg font-bold text-neutral-900 dark:text-white">Knowledge Base Management</h2>
              </div>

              <div className="space-y-6">
                
                {/* Basic Info */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">Basic Info</label>
                  
                  <div className="space-y-4">
                    <AgInput 
                      label="What are you working on?"
                      placeholder="MyKnowledgebase"
                      defaultValue="MyKnowledgebase"
                    />

                    <div>
                      <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">What are you trying to achieve?</label>
                      <textarea 
                        className="w-full h-20 rounded-md border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none resize-none dark:text-neutral-100"
                        defaultValue="A collection of organized, factual documents for quick retrieval. Use this knowledgebase to find authoritative context."
                      />
                    </div>
                  </div>
                </div>

                {/* Add URL */}
                <div className="bg-neutral-50 dark:bg-neutral-800/50 p-4 rounded-lg border border-neutral-100 dark:border-neutral-800">
                  <label className="block text-sm font-bold text-neutral-900 dark:text-white mb-3">Add URL to Knowledge Base</label>
                  <div className="space-y-3">
                    <AgInput 
                      placeholder="https://stackoverflow.com/... or any URL"
                      value={urlInput}
                      onChange={(e) => setUrlInput(e.target.value)}
                    />
                    <button 
                      onClick={handleAddUrl}
                      disabled={isLoading || !urlInput.trim()}
                      className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors w-full md:w-auto flex items-center justify-center gap-2"
                    >
                      {loadingAction === 'url' && <Loader2 size={14} className="animate-spin" />}
                      Add URL to Knowledge Base
                    </button>
                  </div>
                </div>

                {/* Management */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">Management</label>
                  
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs text-neutral-500 mb-2">Knowledge-base status</label>
                      <button 
                        onClick={fetchData}
                        className="flex items-center gap-2 px-3 py-1.5 border border-neutral-300 dark:border-neutral-700 rounded text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800"
                      >
                        <RefreshCw size={14} />
                        Refresh Status
                      </button>
                    </div>

                    <div>
                      <label className="block text-xs text-neutral-500 mb-2">Add documents to knowledge base</label>
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
                            CHOOSE FILES
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
                    </div>

                    <div>
                      <label className="block text-xs text-neutral-500 mb-2">Documents in knowledge base ({documents.length})</label>
                      <div className="border border-neutral-200 dark:border-neutral-700 rounded-md p-2 bg-white dark:bg-neutral-900 max-h-48 overflow-y-auto">
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
                                  <span className="text-xs text-neutral-400">({doc.chunk_count} chunks)</span>
                                </div>
                                <button
                                  onClick={() => handleDeleteDocument(doc.document_id)}
                                  className="opacity-0 group-hover:opacity-100 p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-opacity"
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
                </div>

                {/* Danger Zone */}
                <div>
                  <label className="block text-sm font-bold text-red-600 dark:text-red-400 mb-2">Danger Zone</label>
                  <p className="text-xs text-neutral-500 mb-4">These actions are permanent and cannot be undone. Please proceed with caution.</p>
                  
                  <div className="border border-red-200 dark:border-red-900/50 rounded-lg p-4 bg-red-50/10 dark:bg-red-900/10 space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-neutral-900 dark:text-white">Reingest all documents</div>
                        <div className="text-xs text-neutral-500">Reingests documents in the knowledgebase</div>
                      </div>
                      <button 
                        onClick={handleReingest}
                        disabled={isLoading || documents.length === 0}
                        className="px-3 py-1.5 border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 rounded text-xs font-medium hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors disabled:opacity-50 flex items-center gap-1"
                      >
                        {loadingAction === 'reingest' && <Loader2 size={12} className="animate-spin" />}
                        Reingest documents
                      </button>
                    </div>

                    <div className="h-px bg-red-100 dark:bg-red-900/30 w-full" />

                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-neutral-900 dark:text-white">Reset knowledge base</div>
                        <div className="text-xs text-neutral-500">Resets the knowledge base</div>
                      </div>
                      <button 
                        onClick={handleReset}
                        disabled={isLoading}
                        className="px-3 py-1.5 border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 rounded text-xs font-medium hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors disabled:opacity-50 flex items-center gap-1"
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
    </div>
  );
};
