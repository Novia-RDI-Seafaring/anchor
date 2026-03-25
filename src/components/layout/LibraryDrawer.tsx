"use client";

import React, { useState, useEffect, useCallback } from "react";
import { FileText, Cpu, X, ChevronRight, CheckCircle2, Layers, Trash2 } from "lucide-react";
import { useApp, type KBDocument } from "@/contexts/AppContext";
import { useSession } from "next-auth/react";
import { API_URL } from "@/lib/api-config";

interface LibraryDrawerProps {
  open: boolean;
  onClose: () => void;
  workspaceDocIds: string[];
  onAddDoc: (docId: string) => void;
  onAddFmu: (filename: string) => void;
  onAddSnippet?: (nodes: any[], relations: any[]) => void;
}

type LibTab = "docs" | "fmus" | "snippets";

interface Snippet {
  id: string;
  name: string;
  nodes: any[];
  relations: any[];
  created_at: string;
}

export function LibraryDrawer({ open, onClose, workspaceDocIds, onAddDoc, onAddFmu, onAddSnippet }: LibraryDrawerProps) {
  const { documents } = useApp();
  const { data: session } = useSession();
  const userId = (session?.user as any)?.id ?? 'local-dev-user';
  const userHeaders = { 'x-user-id': userId };

  const [tab, setTab] = useState<LibTab>("docs");
  const [fmuFiles, setFmuFiles] = useState<string[]>([]);
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const wsSet = new Set(workspaceDocIds);

  const loadSnippets = useCallback(() => {
    fetch(`${API_URL}/api/snippets`, { headers: userHeaders })
      .then(r => r.ok ? r.json() : [])
      .then(data => setSnippets(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [userId]);

  useEffect(() => {
    if (!open) return;
    fetch(`${API_URL}/api/fmu/list`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setFmuFiles(data.files ?? []); })
      .catch(() => {});
    loadSnippets();
  }, [open, loadSnippets]);

  const deleteSnippet = useCallback(async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await fetch(`${API_URL}/api/snippets/${id}`, { method: 'DELETE', headers: userHeaders }).catch(() => {});
    setSnippets(prev => prev.filter(s => s.id !== id));
  }, [userHeaders]);

  if (!open) return null;

  return (
    <div className="absolute right-0 top-0 bottom-0 w-72 z-20 flex flex-col bg-white dark:bg-neutral-900 border-l border-neutral-200 dark:border-neutral-800 shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-200 dark:border-neutral-800">
        <span className="text-sm font-semibold text-neutral-800 dark:text-neutral-200">Library</span>
        <button onClick={onClose} className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">
          <X size={16} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-neutral-200 dark:border-neutral-800">
        {(["docs", "fmus", "snippets"] as LibTab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium transition-colors ${
              tab === t
                ? "border-b-2 border-indigo-500 text-indigo-600 dark:text-indigo-400"
                : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
            }`}
          >
            {t === "docs" ? <FileText size={13} /> : t === "fmus" ? <Cpu size={13} /> : <Layers size={13} />}
            {t === "docs" ? "Documents" : t === "fmus" ? "FMUs" : "Snippets"}
            {t === "snippets" && snippets.length > 0 && (
              <span className="text-[10px] bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 px-1 rounded-full">
                {snippets.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-2">
        {tab === "docs" && (
          <>
            {documents.length === 0 && (
              <p className="text-xs text-neutral-400 dark:text-neutral-500 text-center py-8">
                No documents in knowledge base.
              </p>
            )}
            {documents.map(doc => {
              const inWs = wsSet.has(doc.document_id);
              return (
                <div
                  key={doc.document_id}
                  draggable
                  onDragStart={e => {
                    e.dataTransfer.setData("application/anchor-doc", doc.document_id);
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  onClick={() => !inWs && onAddDoc(doc.document_id)}
                  className={`flex items-center gap-2 px-3 py-2.5 rounded-lg mb-1 cursor-grab active:cursor-grabbing select-none transition-colors ${
                    inWs
                      ? "bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800"
                      : "hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-transparent"
                  }`}
                  title={inWs ? "In workspace" : "Drag or click to add to workspace"}
                >
                  <FileText size={14} className={inWs ? "text-emerald-500 shrink-0" : "text-neutral-400 shrink-0"} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate">{doc.filename}</p>
                    <p className="text-[10px] text-neutral-400 dark:text-neutral-500">{doc.node_count} chunks</p>
                  </div>
                  {inWs && <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />}
                  {!inWs && <ChevronRight size={13} className="text-neutral-300 shrink-0" />}
                </div>
              );
            })}
          </>
        )}

        {tab === "fmus" && (
          <>
            {fmuFiles.length === 0 && (
              <p className="text-xs text-neutral-400 dark:text-neutral-500 text-center py-8">
                No FMU files uploaded yet. Drop .fmu files onto the canvas.
              </p>
            )}
            {fmuFiles.map(filename => (
              <div
                key={filename}
                draggable
                onDragStart={e => {
                  e.dataTransfer.setData("application/anchor-fmu", filename);
                  e.dataTransfer.effectAllowed = "copy";
                }}
                onClick={() => onAddFmu(filename)}
                className="flex items-center gap-2 px-3 py-2.5 rounded-lg mb-1 cursor-grab active:cursor-grabbing select-none hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-transparent transition-colors"
                title="Drag or click to add to canvas"
              >
                <Cpu size={14} className="text-teal-500 shrink-0" />
                <p className="flex-1 text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate">{filename}</p>
                <ChevronRight size={13} className="text-neutral-300 shrink-0" />
              </div>
            ))}
          </>
        )}

        {tab === "snippets" && (
          <>
            {snippets.length === 0 && (
              <div className="text-center py-8 px-4">
                <Layers size={24} className="text-neutral-300 dark:text-neutral-600 mx-auto mb-2" />
                <p className="text-xs text-neutral-400 dark:text-neutral-500">
                  No snippets saved yet.
                </p>
                <p className="text-[10px] text-neutral-300 dark:text-neutral-600 mt-1">
                  Select nodes on the canvas and click "Save to library".
                </p>
              </div>
            )}
            {snippets.map(snippet => (
              <div
                key={snippet.id}
                draggable
                onDragStart={e => {
                  e.dataTransfer.setData("application/anchor-snippet", JSON.stringify({ nodes: snippet.nodes, relations: snippet.relations }));
                  e.dataTransfer.effectAllowed = "copy";
                }}
                onClick={() => onAddSnippet?.(snippet.nodes, snippet.relations)}
                className="group flex items-center gap-2 px-3 py-2.5 rounded-lg mb-1 cursor-grab active:cursor-grabbing select-none hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-transparent transition-colors"
                title="Drag or click to add to canvas"
              >
                <Layers size={14} className="text-indigo-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate">{snippet.name}</p>
                  <p className="text-[10px] text-neutral-400 dark:text-neutral-500">
                    {snippet.nodes.length} node{snippet.nodes.length !== 1 ? 's' : ''}
                  </p>
                </div>
                <button
                  onClick={e => deleteSnippet(snippet.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:text-red-500 text-neutral-400 transition-opacity"
                  title="Delete snippet"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="px-4 py-3 border-t border-neutral-200 dark:border-neutral-800">
        <p className="text-[10px] text-neutral-400 dark:text-neutral-500">
          Drag items onto the canvas to add them to your workspace.
        </p>
      </div>
    </div>
  );
}
