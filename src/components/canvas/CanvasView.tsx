"use client";

import React, { useState } from "react";
import { FileText, X, ChevronDown, ChevronRight, BookOpen, MapPin } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

// --- Types mirroring backend state.py ---
interface Source {
  filename: string;
  page: number;
}

interface SourceBox {
  source: Source;
  bbox: number[]; // [left, top, right, bottom]
}

interface Fact {
  text: string;
  sources: SourceBox[];
}

interface Note {
  title: string;
  facts: Fact[];
}

interface CanvasState {
  notes: Note[];
}

// Build the bbox screenshot URL (mirrors the Python @property)
function buildImageUrl(sb: SourceBox): string {
  const { filename, page } = sb.source;
  const [l, t, r, b] = sb.bbox;
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}&bbox_l=${l}&bbox_t=${t}&bbox_r=${r}&bbox_b=${b}`;
}

function buildPageUrl(filename: string, page: number): string {
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}`;
}

// --- Lightbox ---
interface LightboxProps {
  url: string;
  caption: string;
  onClose: () => void;
}

function Lightbox({ url, caption, onClose }: LightboxProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative max-w-3xl w-full bg-white dark:bg-neutral-900 rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <span className="text-xs font-mono text-neutral-500 dark:text-neutral-400 truncate">{caption}</span>
          <button
            onClick={onClose}
            className="ml-2 p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500 dark:text-neutral-400"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex items-center justify-center bg-neutral-100 dark:bg-neutral-950 p-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={caption}
            className="max-h-[70vh] w-auto object-contain rounded"
          />
        </div>
      </div>
    </div>
  );
}

// --- SourceChip — small thumbnail badge for a SourceBox ---
interface SourceChipProps {
  sb: SourceBox;
  index: number;
}

function SourceChip({ sb, index }: SourceChipProps) {
  const [lightbox, setLightbox] = useState<{ url: string; caption: string } | null>(null);
  const imgUrl = buildImageUrl(sb);
  const caption = `${sb.source.filename} — p.${sb.source.page} [${sb.bbox.join(", ")}]`;

  return (
    <>
      <button
        onClick={() => setLightbox({ url: imgUrl, caption })}
        className="group flex items-center gap-1.5 px-2 py-1 rounded-md bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-100 dark:border-indigo-800 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 transition-colors"
        title={caption}
      >
        <MapPin size={11} className="text-indigo-500 dark:text-indigo-400 shrink-0" />
        <span className="text-[11px] font-mono text-indigo-700 dark:text-indigo-300 truncate max-w-[140px]">
          {sb.source.filename.replace(/\.pdf$/i, "")} p.{sb.source.page}
        </span>
        {/* Tiny preview thumbnail */}
        <span className="relative shrink-0 w-8 h-8 rounded overflow-hidden border border-indigo-200 dark:border-indigo-700 bg-white dark:bg-neutral-900">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imgUrl}
            alt=""
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-150"
            loading="lazy"
          />
        </span>
      </button>

      {lightbox && (
        <Lightbox
          url={lightbox.url}
          caption={lightbox.caption}
          onClose={() => setLightbox(null)}
        />
      )}
    </>
  );
}

// --- FactRow ---
interface FactRowProps {
  fact: Fact;
  index: number;
}

function FactRow({ fact, index }: FactRowProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="border-l-2 border-neutral-200 dark:border-neutral-700 pl-3 py-1 space-y-2">
      {/* Fact text */}
      <div className="flex items-start gap-2">
        <span className="shrink-0 mt-0.5 text-[10px] font-mono text-neutral-400 dark:text-neutral-500 w-4 text-right select-none">
          {index + 1}.
        </span>
        <p className="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed flex-1">
          {fact.text}
        </p>
      </div>

      {/* Sources */}
      {fact.sources.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-6">
          {fact.sources.map((sb, si) => (
            <SourceChip key={si} sb={sb} index={si} />
          ))}
        </div>
      )}
    </div>
  );
}

// --- NoteCard ---
interface NoteCardProps {
  note: Note;
  index: number;
}

function NoteCard({ note, index }: NoteCardProps) {
  const [collapsed, setCollapsed] = useState(false);
  const factCount = note.facts.length;
  const sourceCount = note.facts.reduce((n, f) => n + f.sources.length, 0);

  return (
    <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      {/* Note header */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
        onClick={() => setCollapsed((c) => !c)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div className="h-7 w-7 rounded-lg bg-amber-50 dark:bg-amber-900/30 flex items-center justify-center shrink-0">
            <BookOpen size={14} className="text-amber-600 dark:text-amber-400" />
          </div>
          <span className="font-semibold text-sm text-neutral-900 dark:text-white truncate">
            {note.title}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <span className="text-[11px] text-neutral-400 dark:text-neutral-500 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded-full">
            {factCount} fact{factCount !== 1 ? "s" : ""}
          </span>
          {sourceCount > 0 && (
            <span className="text-[11px] text-indigo-500 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/30 px-2 py-0.5 rounded-full">
              {sourceCount} src
            </span>
          )}
          {collapsed ? (
            <ChevronRight size={14} className="text-neutral-400" />
          ) : (
            <ChevronDown size={14} className="text-neutral-400" />
          )}
        </div>
      </button>

      {/* Facts list */}
      {!collapsed && (
        <div className="px-4 pb-4 space-y-3 border-t border-neutral-100 dark:border-neutral-800 pt-3">
          {note.facts.length === 0 ? (
            <p className="text-xs text-neutral-400 dark:text-neutral-500 italic">No facts yet.</p>
          ) : (
            note.facts.map((fact, fi) => (
              <FactRow key={fi} fact={fact} index={fi} />
            ))
          )}
        </div>
      )}
    </div>
  );
}

// --- Empty state ---
function EmptyCanvas() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="h-16 w-16 rounded-2xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center mb-4">
        <FileText size={28} className="text-neutral-400 dark:text-neutral-500" />
      </div>
      <h3 className="text-base font-semibold text-neutral-700 dark:text-neutral-300 mb-1">Canvas is empty</h3>
      <p className="text-sm text-neutral-400 dark:text-neutral-500 max-w-xs">
        Ask the agent to research a topic — it will populate notes with sourced facts here.
      </p>
    </div>
  );
}

// --- Main CanvasView export ---
interface CanvasViewProps {
  canvas: CanvasState | null | undefined;
}

export function CanvasView({ canvas }: CanvasViewProps) {
  const notes = canvas?.notes ?? [];

  if (notes.length === 0) {
    return <EmptyCanvas />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-neutral-900 dark:text-white uppercase tracking-wider">
            Canvas
          </h2>
          <span className="text-[11px] text-neutral-400 dark:text-neutral-500 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded-full">
            {notes.length} note{notes.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {notes.map((note, i) => (
          <NoteCard key={i} note={note} index={i} />
        ))}
      </div>
    </div>
  );
}
