"use client";

import React, { useState, useCallback } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { BookOpen, FileText, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import type { PDFHighlight } from "./PDFModal";

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

// --- Types ---
interface Source {
  filename: string;
  page: number;
}

interface SourceBox {
  source: Source;
  bbox: number[];
}

interface Fact {
  text: string;
  sources: SourceBox[];
}

export interface NoteData {
  id: string;
  title: string;
  facts: Fact[];
}

export interface NoteNodeData {
  note: NoteData;
  onOpenPDF: (filename: string, page: number, highlights: PDFHighlight[]) => void;
}

// --- URL helpers ---
function bboxUrl(sb: SourceBox): string {
  const [l, t, r, b] = sb.bbox;
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(sb.source.filename)}&page_no=${sb.source.page}&bbox_l=${l}&bbox_t=${t}&bbox_r=${r}&bbox_b=${b}`;
}

function pageThumbUrl(filename: string, page: number): string {
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}`;
}

// --- Source thumbnail ---
function SourceThumb({
  sb,
  onOpenPDF,
  allHighlights,
}: {
  sb: SourceBox;
  onOpenPDF: NoteNodeData["onOpenPDF"];
  allHighlights: PDFHighlight[];
}) {
  return (
    <button
      onClick={() => onOpenPDF(sb.source.filename, sb.source.page, allHighlights)}
      className="group flex flex-col gap-1 focus:outline-none"
      title={`${sb.source.filename} p.${sb.source.page} — open PDF`}
    >
      {/* Cropped bbox screenshot with full-page thumb overlay */}
      <div className="relative w-[76px] h-[54px] rounded overflow-hidden border-2 border-indigo-200 dark:border-indigo-700 group-hover:border-indigo-400 transition-colors shadow-sm">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={bboxUrl(sb)}
          alt=""
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-150"
          loading="lazy"
        />
        {/* Full-page thumbnail in corner */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={pageThumbUrl(sb.source.filename, sb.source.page)}
          alt=""
          className="absolute bottom-0.5 right-0.5 w-7 h-9 object-cover rounded border border-white dark:border-neutral-700 shadow-md"
          loading="lazy"
        />
        {/* Page badge */}
        <div className="absolute top-0.5 left-0.5 flex items-center gap-0.5 bg-black/60 rounded px-1 py-0.5">
          <FileText size={7} className="text-white" />
          <span className="text-[8px] text-white font-mono leading-none">{sb.source.page}</span>
        </div>
        {/* Open PDF icon on hover */}
        <div className="absolute inset-0 bg-indigo-600/0 group-hover:bg-indigo-600/10 transition-colors flex items-center justify-center">
          <ExternalLink
            size={14}
            className="text-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-md"
          />
        </div>
      </div>
      <span className="text-[9px] text-neutral-400 font-mono truncate w-[76px] text-center">
        {sb.source.filename.replace(/\.pdf$/i, "")}
      </span>
    </button>
  );
}

// --- The node ---
export function NoteNode({ data }: NodeProps) {
  const { note, onOpenPDF } = data as unknown as NoteNodeData;
  const [expanded, setExpanded] = useState(false);

  const factCount = note.facts.length;
  const sourceCount = note.facts.reduce((n, f) => n + f.sources.length, 0);

  // All highlights from all facts in this note (for PDF modal)
  const allHighlights: PDFHighlight[] = note.facts.flatMap((f) =>
    f.sources.map((sb) => ({ page: sb.source.page, bbox: sb.bbox }))
  );

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-indigo-400 !border-indigo-600" />
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-400 !border-indigo-600" />

      <div
        className={`bg-white dark:bg-neutral-900 border-2 rounded-xl shadow-lg transition-all duration-200 ${
          expanded
            ? "border-indigo-400 dark:border-indigo-500"
            : "border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600"
        }`}
        style={{ width: expanded ? 340 : 240 }}
      >
        {/* Header */}
        <button
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-t-xl hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
          onClick={() => setExpanded((e) => !e)}
        >
          <div className="h-6 w-6 rounded-md bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center shrink-0">
            <BookOpen size={12} className="text-amber-600 dark:text-amber-400" />
          </div>
          <span className="flex-1 text-left text-sm font-semibold text-neutral-900 dark:text-white truncate">
            {note.title}
          </span>
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-[10px] bg-neutral-100 dark:bg-neutral-800 text-neutral-400 px-1.5 py-0.5 rounded-full">
              {factCount}f
            </span>
            {sourceCount > 0 && (
              <span className="text-[10px] bg-indigo-50 dark:bg-indigo-900/30 text-indigo-500 dark:text-indigo-400 px-1.5 py-0.5 rounded-full">
                {sourceCount}s
              </span>
            )}
            {expanded ? (
              <ChevronUp size={12} className="text-neutral-400" />
            ) : (
              <ChevronDown size={12} className="text-neutral-400" />
            )}
          </div>
        </button>

        {/* Expanded facts */}
        {expanded && (
          <div className="border-t border-neutral-100 dark:border-neutral-800 px-3 pb-3 pt-2 space-y-3 max-h-80 overflow-y-auto">
            {note.facts.length === 0 ? (
              <p className="text-xs text-neutral-400 italic">No facts.</p>
            ) : (
              note.facts.map((fact, fi) => (
                <div key={fi} className="space-y-2">
                  <p className="text-xs text-neutral-700 dark:text-neutral-300 leading-relaxed">
                    <span className="text-neutral-400 mr-1 font-mono">{fi + 1}.</span>
                    {fact.text}
                  </p>
                  {fact.sources.length > 0 && (
                    <div className="flex flex-wrap gap-2 pl-4">
                      {fact.sources.map((sb, si) => (
                        <SourceThumb
                          key={si}
                          sb={sb}
                          onOpenPDF={onOpenPDF}
                          allHighlights={allHighlights}
                        />
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </>
  );
}
