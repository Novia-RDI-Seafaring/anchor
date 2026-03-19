"use client";

import React, { useState, useEffect } from "react";
import { FileText, Cpu, X, ChevronRight, CheckCircle2 } from "lucide-react";
import { useApp, type KBDocument } from "@/contexts/AppContext";
import { API_URL } from "@/lib/api-config";

interface LibraryDrawerProps {
  open: boolean;
  onClose: () => void;
  workspaceDocIds: string[];
  onAddDoc: (docId: string) => void;
  onAddFmu: (filename: string) => void;
}

type LibTab = "docs" | "fmus";

export function LibraryDrawer({ open, onClose, workspaceDocIds, onAddDoc, onAddFmu }: LibraryDrawerProps) {
  const { documents } = useApp();
  const [tab, setTab] = useState<LibTab>("docs");
  const [fmuFiles, setFmuFiles] = useState<string[]>([]);
  const wsSet = new Set(workspaceDocIds);

  useEffect(() => {
    if (!open) return;
    fetch(`${API_URL}/api/fmu/list`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setFmuFiles(data.files ?? []); })
      .catch(() => {});
  }, [open]);

  if (!open) return null;

  return (
    <div className="absolute right-0 top-0 bottom-0 w-72 z-20 flex flex-col bg-white dark:bg-neutral-900 border-l border-neutral-200 dark:border-neutral-800 shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-200 dark:border-neutral-800">
        <span className="text-sm font-semibold text-neutral-800 dark:text-neutral-200">Library</span>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500"
        >
          <X size={16} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-neutral-200 dark:border-neutral-800">
        {(["docs", "fmus"] as LibTab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium transition-colors ${
              tab === t
                ? "border-b-2 border-indigo-500 text-indigo-600 dark:text-indigo-400"
                : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
            }`}
          >
            {t === "docs" ? <FileText size={13} /> : <Cpu size={13} />}
            {t === "docs" ? "Documents" : "FMUs"}
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
                    <p className="text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate">
                      {doc.filename}
                    </p>
                    <p className="text-[10px] text-neutral-400 dark:text-neutral-500">
                      {doc.node_count} chunks
                    </p>
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
                <p className="flex-1 text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate">
                  {filename}
                </p>
                <ChevronRight size={13} className="text-neutral-300 shrink-0" />
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
