"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { FileText, Cpu, Layers, CheckCircle2, Trash2, X } from "lucide-react";
import { useApp, type KBDocument } from "@/contexts/AppContext";
import { useSession } from "next-auth/react";
import { API_URL, writeApiHeaders } from "@/lib/api-config";

export type PaletteTab = "docs" | "fmus" | "snippets";

interface Snippet {
  id: string;
  name: string;
  nodes: any[];
  relations: any[];
  created_at: string;
}

function setCustomDragPreview(
  event: React.DragEvent<HTMLElement>,
  options: { label: string; width: number; height: number; className: string; caption?: string },
) {
  const preview = document.createElement("div");
  preview.className = `fixed -left-[9999px] -top-[9999px] pointer-events-none rounded-xl border-2 shadow-xl ${options.className}`;
  preview.style.width = `${options.width}px`;
  preview.style.minHeight = `${options.height}px`;
  preview.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:4px;padding:12px 14px;">
      <div style="font-size:13px;font-weight:700;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${options.label}</div>
      ${options.caption ? `<div style="font-size:11px;opacity:0.72;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${options.caption}</div>` : ""}
    </div>
  `;
  document.body.appendChild(preview);
  event.dataTransfer.setDragImage(preview, options.width / 2, Math.min(options.height / 2, 32));
  requestAnimationFrame(() => preview.remove());
}

export interface ResourcePaletteProps {
  tab: PaletteTab;
  anchorY: number;
  workspaceDocIds: string[];
  onAddDoc: (docId: string) => void;
  onAddFmu: (filename: string) => void;
  onAddSnippet?: (nodes: any[], relations: any[]) => void;
  onClose: () => void;
}

export function ResourcePalette({
  tab,
  anchorY,
  workspaceDocIds,
  onAddDoc,
  onAddFmu,
  onAddSnippet,
  onClose,
}: ResourcePaletteProps) {
  const { documents } = useApp();
  const { data: session } = useSession();
  const userId = (session?.user as any)?.id ?? "local-dev-user";
  const userHeaders = { "x-user-id": userId };
  const wsSet = new Set(workspaceDocIds);
  const panelRef = useRef<HTMLDivElement>(null);

  const [fmuFiles, setFmuFiles] = useState<string[]>([]);
  const [snippets, setSnippets] = useState<Snippet[]>([]);

  const loadSnippets = useCallback(() => {
    fetch(`${API_URL}/api/snippets`, { headers: userHeaders })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setSnippets(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [userId]);

  useEffect(() => {
    if (tab === "fmus") {
      fetch(`${API_URL}/api/fmu/list`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => { if (data) setFmuFiles(data.files ?? []); })
        .catch(() => {});
    }
    if (tab === "snippets") loadSnippets();
  }, [tab, loadSnippets]);

  const deleteSnippet = useCallback(
    async (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      await fetch(`${API_URL}/api/snippets/${id}`, { method: "DELETE", headers: writeApiHeaders(userHeaders) }).catch(() => {});
      setSnippets((prev) => prev.filter((s) => s.id !== id));
    },
    [userHeaders],
  );

  // Close on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Delay so the toolbar click that opened us doesn't immediately close
    const timer = setTimeout(() => document.addEventListener("mousedown", handler), 50);
    return () => { clearTimeout(timer); document.removeEventListener("mousedown", handler); };
  }, [onClose]);

  const title = tab === "docs" ? "Documents" : tab === "fmus" ? "FMU Models" : "Snippets";
  const icon = tab === "docs" ? <FileText size={14} /> : tab === "fmus" ? <Cpu size={14} /> : <Layers size={14} />;

  // Clamp so the palette doesn't go off-screen
  const maxTop = typeof window !== "undefined" ? window.innerHeight - 360 : 400;
  const top = Math.min(anchorY, maxTop);

  return (
    <div
      ref={panelRef}
      className="absolute z-40 w-64 max-h-[340px] flex flex-col bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-2xl shadow-[0_14px_40px_rgba(15,23,42,0.12)] backdrop-blur-md overflow-hidden"
      style={{ left: 72, top }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-neutral-100 dark:border-neutral-800">
        <span className="text-neutral-400">{icon}</span>
        <span className="text-xs font-semibold text-neutral-700 dark:text-neutral-200 flex-1">{title}</span>
        <button onClick={onClose} className="p-0.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-400">
          <X size={14} />
        </button>
      </div>

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto p-1.5">
        {tab === "docs" && (
          <>
            {documents.length === 0 && (
              <p className="text-[11px] text-neutral-400 text-center py-6">No documents in knowledge base.</p>
            )}
            {documents.map((doc) => {
              const inWs = wsSet.has(doc.document_id);
              return (
                <div
                  key={doc.document_id}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("application/anchor-doc", doc.document_id);
                    e.dataTransfer.effectAllowed = "copy";
                    setCustomDragPreview(e, {
                      label: doc.filename,
                      caption: `${doc.node_count} chunks`,
                      width: 280,
                      height: 120,
                      className: inWs
                        ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                        : "bg-white border-neutral-200 text-neutral-900",
                    });
                  }}
                  onDragEnd={onClose}
                  onClick={() => !inWs && onAddDoc(doc.document_id)}
                  className={`flex items-center gap-2 px-2.5 py-2 rounded-xl mb-0.5 cursor-grab active:cursor-grabbing select-none transition-colors ${
                    inWs
                      ? "bg-emerald-50/70 dark:bg-emerald-950/25 border border-emerald-200/60 dark:border-emerald-800/40"
                      : "hover:bg-neutral-50 dark:hover:bg-neutral-800 border border-transparent"
                  }`}
                  title={inWs ? "In workspace" : "Drag or click to add"}
                >
                  <FileText size={13} className={inWs ? "text-emerald-500 shrink-0" : "text-neutral-400 shrink-0"} />
                  <div className="flex-1 min-w-0">
                    <p className="text-[11px] font-medium text-neutral-800 dark:text-neutral-200 truncate">{doc.filename}</p>
                    <p className="text-[10px] text-neutral-400 dark:text-neutral-500">{doc.node_count} chunks</p>
                  </div>
                  {inWs && <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />}
                </div>
              );
            })}
          </>
        )}

        {tab === "fmus" && (
          <>
            {fmuFiles.length === 0 && (
              <p className="text-[11px] text-neutral-400 text-center py-6">No FMU files. Drop .fmu onto canvas.</p>
            )}
            {fmuFiles.map((filename) => (
              <div
                key={filename}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/anchor-fmu", filename);
                  e.dataTransfer.effectAllowed = "copy";
                  setCustomDragPreview(e, {
                    label: filename,
                    caption: "FMU model",
                    width: 260,
                    height: 92,
                    className: "bg-teal-50 border-teal-300 text-teal-950",
                  });
                  onClose();
                }}
                onClick={() => onAddFmu(filename)}
                className="flex items-center gap-2 px-2.5 py-2 rounded-xl mb-0.5 cursor-grab active:cursor-grabbing select-none hover:bg-neutral-50 dark:hover:bg-neutral-800 border border-transparent transition-colors"
                title="Drag or click to add"
              >
                <Cpu size={13} className="text-teal-500 shrink-0" />
                <p className="flex-1 text-[11px] font-medium text-neutral-800 dark:text-neutral-200 truncate">{filename}</p>
              </div>
            ))}
          </>
        )}

        {tab === "snippets" && (
          <>
            {snippets.length === 0 && (
              <div className="text-center py-6 px-3">
                <Layers size={20} className="text-neutral-300 dark:text-neutral-600 mx-auto mb-1.5" />
                <p className="text-[11px] text-neutral-400">No snippets saved yet.</p>
                <p className="text-[10px] text-neutral-300 dark:text-neutral-600 mt-0.5">Select nodes &rarr; Save to library</p>
              </div>
            )}
            {snippets.map((snippet) => (
              <div
                key={snippet.id}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(
                    "application/anchor-snippet",
                    JSON.stringify({ nodes: snippet.nodes, relations: snippet.relations }),
                  );
                  e.dataTransfer.effectAllowed = "copy";
                  setCustomDragPreview(e, {
                    label: snippet.name,
                    caption: `${snippet.nodes.length} node${snippet.nodes.length !== 1 ? "s" : ""}`,
                    width: 220,
                    height: 84,
                    className: "bg-indigo-50 border-indigo-300 text-indigo-950",
                  });
                  onClose();
                }}
                onClick={() => onAddSnippet?.(snippet.nodes, snippet.relations)}
                className="group flex items-center gap-2 px-2.5 py-2 rounded-xl mb-0.5 cursor-grab active:cursor-grabbing select-none hover:bg-neutral-50 dark:hover:bg-neutral-800 border border-transparent transition-colors"
                title="Drag or click to add"
              >
                <Layers size={13} className="text-indigo-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-medium text-neutral-800 dark:text-neutral-200 truncate">{snippet.name}</p>
                  <p className="text-[10px] text-neutral-400 dark:text-neutral-500">
                    {snippet.nodes.length} node{snippet.nodes.length !== 1 ? "s" : ""}
                  </p>
                </div>
                <button
                  onClick={(e) => deleteSnippet(snippet.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:text-red-500 text-neutral-400 transition-opacity"
                  title="Delete snippet"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
