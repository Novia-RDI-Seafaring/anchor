import React, { useState } from 'react';
import { 
  ArrowLeft, 
  Bot, 
  Settings2, 
  Save, 
  Database, 
  Check, 
  X, 
  FileText, 
  HardDrive, 
  Globe, 
  Layout, 
  Trash2, 
  RefreshCw,
  AlertTriangle
} from 'lucide-react';
import { AgCard, AgButton, AgInput, AgSelect, AgBadge } from '../ui/AgComponents';

interface SettingsPageProps {
  onBack: () => void;
}

const Toggle: React.FC<{ checked: boolean; onChange: (checked: boolean) => void; label?: string }> = ({ checked, onChange, label }) => (
  <button 
    onClick={() => onChange(!checked)}
    className="flex items-center justify-between w-full group"
  >
    {label && <span className="text-sm text-neutral-700">{label}</span>}
    <div className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${checked ? 'bg-brand-600' : 'bg-neutral-200'}`}>
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${checked ? 'translate-x-6' : 'translate-x-1'}`} />
    </div>
  </button>
);

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

  return (
    <div className="flex-1 h-full bg-neutral-50/50 overflow-y-auto p-4 md:p-8 animate-in fade-in slide-in-from-bottom-4 duration-300">
      <div className="max-w-7xl mx-auto">
        
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button 
            onClick={onBack}
            className="p-2 hover:bg-neutral-200 rounded-full text-neutral-600 transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="flex items-center gap-2 text-xl font-bold text-neutral-900">
            <Settings2 className="h-6 w-6" />
            <h1>Settings</h1>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          
          {/* Column 1: AI Assistant Configuration */}
          <div className="space-y-6">
            <AgCard className="p-6 border-neutral-200 shadow-sm">
              <div className="flex items-center gap-2 mb-6">
                <div className="h-8 w-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Bot size={20} />
                </div>
                <h2 className="text-lg font-bold text-neutral-900">AI Assistant Configuration</h2>
              </div>

              <div className="space-y-6">
                
                {/* System Prompt */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 mb-2">Configuration</label>
                  <label className="block text-xs text-neutral-500 mb-1">System Prompt</label>
                  <textarea 
                    className="w-full h-24 rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none resize-none"
                    defaultValue="You are a knowledgeable and helpful assistant. CRITICAL: You must ONLY use information from the provided documents to answer questions."
                  />
                  <p className="text-xs text-neutral-500 mt-1">This defines how your AI agent will behave and respond to questions.</p>
                </div>

                {/* Model Selection */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 mb-2">Model Selection</label>
                  <label className="block text-xs text-neutral-500 mb-1">Select AI Model</label>
                  <AgSelect 
                    options={[{ id: 'llama3.2', label: 'LlamaStack - ollama/llama3.2:3b' }]}
                    value="llama3.2"
                    onChange={() => {}}
                    className="w-full"
                  />
                  <div className="flex items-center gap-1.5 mt-2 text-xs text-emerald-600">
                    <Check size={12} strokeWidth={3} />
                    <span>Found 4 available model(s)</span>
                  </div>
                </div>

                {/* Advanced Settings */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 mb-4">Advanced Settings</label>
                  
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
                  <label className="block text-sm font-semibold text-neutral-700 mb-2">MCP Tools</label>
                  <p className="text-xs text-neutral-500 mb-4">Select which MCP (Model Context Protocol) tools to enable for your agent:</p>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between py-2">
                       <div className="flex items-center gap-2">
                         <div className="h-5 w-5 rounded border border-neutral-300"></div> {/* Checkbox placeholder */}
                         <span className="text-sm font-medium text-neutral-700">Enable MCP Tools</span>
                       </div>
                    </div>

                    <div className="space-y-2 bg-neutral-50 p-4 rounded-lg border border-neutral-100">
                      <div className="flex items-center justify-between p-2 bg-white rounded border border-neutral-100">
                        <div className="flex items-center gap-2">
                          <HardDrive size={16} className="text-purple-400" />
                          <div>
                            <div className="text-sm font-medium text-neutral-700">Filesystem</div>
                            <div className="text-[10px] text-neutral-400">Endpoint: http://localhost:8000/sse</div>
                          </div>
                        </div>
                        <Toggle checked={mcpTools.filesystem} onChange={(c) => setMcpTools({...mcpTools, filesystem: c})} />
                      </div>

                      <div className="flex items-center justify-between p-2 bg-white rounded border border-neutral-100">
                        <div className="flex items-center gap-2">
                          <Globe size={16} className="text-purple-400" />
                          <div>
                            <div className="text-sm font-medium text-neutral-700">Web_Search</div>
                            <div className="text-[10px] text-neutral-400">Endpoint: https://mcp.search-provider.com/sse</div>
                          </div>
                        </div>
                        <Toggle checked={mcpTools.webSearch} onChange={(c) => setMcpTools({...mcpTools, webSearch: c})} />
                      </div>

                      <div className="flex items-center justify-between p-2 bg-white rounded border border-neutral-100">
                        <div className="flex items-center gap-2">
                          <Database size={16} className="text-purple-400" />
                          <div>
                            <div className="text-sm font-medium text-neutral-700">Database</div>
                            <div className="text-[10px] text-neutral-400">Endpoint:</div>
                          </div>
                        </div>
                        <Toggle checked={mcpTools.database} onChange={(c) => setMcpTools({...mcpTools, database: c})} />
                      </div>

                      <div className="flex items-center justify-between p-2 bg-white rounded border border-neutral-100">
                        <div className="flex items-center gap-2">
                          <Layout size={16} className="text-purple-400" />
                          <div>
                            <div className="text-sm font-medium text-neutral-700">Markitdown</div>
                            <div className="text-[10px] text-neutral-400">Endpoint: http://localhost:8001/sse</div>
                          </div>
                        </div>
                        <Toggle checked={mcpTools.markitdown} onChange={(c) => setMcpTools({...mcpTools, markitdown: c})} />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Status Section */}
                <div>
                   <label className="block text-sm font-semibold text-neutral-700 mb-3">Status</label>
                   <label className="block text-xs text-neutral-500 mb-2">Current Configuration</label>
                   
                   <div className="bg-neutral-50 rounded-lg p-4 space-y-2 text-sm border border-neutral-100">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700">System Prompt:</span>
                        <span className="text-emerald-600">Configured</span>
                        <Check size={14} className="text-emerald-500" />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700">Selected Model:</span>
                        <span className="text-emerald-600">ollama/llama3.2:3b</span>
                        <Check size={14} className="text-emerald-500" />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700">Temperature:</span>
                        <span className="text-neutral-600">{temperature}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700">Max Tokens:</span>
                        <span className="text-neutral-600">{maxTokens}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700">MCP Tools:</span>
                        <span className="text-red-500">Disabled</span>
                        <X size={14} className="text-red-500" />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-700">Knowledge Base:</span>
                        <span className="text-emerald-600">Enabled</span>
                        <Check size={14} className="text-emerald-500" />
                      </div>
                   </div>
                </div>

              </div>
            </AgCard>
          </div>

          {/* Column 2: Knowledge Base Management */}
          <div className="space-y-6">
            <AgCard className="p-6 border-neutral-200 shadow-sm">
              <div className="flex items-center gap-2 mb-6">
                <div className="h-8 w-8 rounded-lg bg-orange-50 text-orange-600 flex items-center justify-center">
                  <Database size={20} />
                </div>
                <h2 className="text-lg font-bold text-neutral-900">Knowledge Base Management</h2>
              </div>

              <div className="space-y-6">
                
                {/* Basic Info */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 mb-3">Basic Info</label>
                  
                  <div className="space-y-4">
                    <AgInput 
                      label="What are you working on?"
                      placeholder="MyKnowledgebase"
                    />

                    <div>
                      <label className="block text-sm font-medium text-neutral-700 mb-1">What are you trying to achieve?</label>
                      <textarea 
                        className="w-full h-20 rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none resize-none"
                        defaultValue="A collection of organized, factual documents for quick retrieval. Use this knowledgebase to find authoritative context."
                      />
                    </div>
                  </div>
                </div>

                {/* Documents Directory */}
                <div>
                  <label className="block text-xs text-neutral-500 mb-1">Documents directory</label>
                  <AgInput 
                    placeholder="C:\Users\lamjat\Documents\Novia_Work_Projects\2025\KB\d"
                    disabled
                    className="bg-neutral-50 text-neutral-500"
                  />
                  <p className="text-xs text-neutral-500 mt-1">Configure DOCUMENTS_DIR in .env file</p>
                </div>

                {/* Add URL */}
                <div className="bg-neutral-50 p-4 rounded-lg border border-neutral-100">
                  <label className="block text-sm font-bold text-neutral-900 mb-3">Add URL to Knowledge Base</label>
                  <div className="space-y-3">
                    <AgInput placeholder="https://stackoverflow.com/... or any URL" />
                    <button className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors w-full md:w-auto">
                      Add URL to Knowledge Base
                    </button>
                  </div>
                </div>

                {/* Management */}
                <div>
                  <label className="block text-sm font-semibold text-neutral-700 mb-3">Management</label>
                  
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs text-neutral-500 mb-2">Knowledge-base status</label>
                      <button className="flex items-center gap-2 px-3 py-1.5 border border-neutral-300 rounded text-sm font-medium text-neutral-700 hover:bg-neutral-50">
                        <Settings2 size={14} />
                        Check Status
                      </button>
                    </div>

                    <div>
                      <label className="block text-xs text-neutral-500 mb-2">Add documents to knowledge base</label>
                      <div className="flex rounded-md shadow-sm">
                        <button className="relative inline-flex items-center rounded-l-md bg-neutral-800 px-3 py-2 text-sm font-semibold text-white hover:bg-neutral-700 focus:z-10">
                          CHOOSE FILES
                        </button>
                        <div className="relative -ml-px flex w-full items-center rounded-r-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-500">
                          No file chosen
                        </div>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs text-neutral-500 mb-2">Documents in knowledge base</label>
                      <div className="border border-neutral-200 rounded-md p-2 bg-white">
                        <div className="flex items-center gap-2 px-2 py-1 text-sm text-neutral-700 bg-neutral-50 rounded">
                           <FileText size={14} className="text-neutral-400" />
                           dummy.pdf
                        </div>
                      </div>
                    </div>

                  </div>
                </div>

                {/* Danger Zone */}
                <div>
                  <label className="block text-sm font-bold text-red-600 mb-2">Danger Zone</label>
                  <p className="text-xs text-neutral-500 mb-4">These actions are permanent and cannot be undone. Please proceed with caution.</p>
                  
                  <div className="border border-red-200 rounded-lg p-4 bg-red-50/10 space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-neutral-900">Reingest all documents</div>
                        <div className="text-xs text-neutral-500">Reingests documents in the knowledgebase</div>
                      </div>
                      <button className="px-3 py-1.5 border border-red-200 text-red-600 rounded text-xs font-medium hover:bg-red-50 transition-colors">
                        Reingest documents
                      </button>
                    </div>

                    <div className="h-px bg-red-100 w-full" />

                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-neutral-900">Reset knowledge base</div>
                        <div className="text-xs text-neutral-500">Resets the knowledge base</div>
                      </div>
                      <button className="px-3 py-1.5 border border-red-200 text-red-600 rounded text-xs font-medium hover:bg-red-50 transition-colors">
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