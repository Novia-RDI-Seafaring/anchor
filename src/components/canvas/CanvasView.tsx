"use client";

import React, { useState } from "react";
import { FileText, X, ChevronDown, ChevronRight, Tag, MessageSquare, MapPin } from "lucide-react";
import type { CanvasNodeData } from "./KnowledgeNodes";

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

interface Relation {
  from_id: string;
  to_id: string;
  label: string;
}

interface CanvasState {
  nodes: CanvasNodeData[];
  relations: Relation[];
}

function buildImageUrl(filename: string, page: number, bbox: number[]): string {
  const [l = 0, t = 0, r = 0, b = 0] = bbox;
  if (!l && !t && !r && !b) {
    return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}`;
  }
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}&bbox_l=${l}&bbox_t=${t}&bbox_r=${r}&bbox_b=${b}`;
}

// --- Lightbox ---
function Lightbox({ url, caption, onClose }: { url: string; caption: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="relative max-w-3xl w-full bg-white dark:bg-neutral-900 rounded-xl shadow-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <span className="text-xs font-mono text-neutral-500 truncate">{caption}</span>
          <button onClick={onClose} className="ml-2 p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">
            <X size={16} />
          </button>
        </div>
        <div className="flex items-center justify-center bg-neutral-100 dark:bg-neutral-950 p-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url} alt={caption} className="max-h-[70vh] w-auto object-contain rounded" />
        </div>
      </div>
    </div>
  );
}

// --- Source chip ---
function SourceChip({ node }: { node: CanvasNodeData }) {
  const [lightbox, setLightbox] = useState<{ url: string; caption: string } | null>(null);
  if (!node.filename) return null;
  const imgUrl = buildImageUrl(node.filename, node.page ?? 1, node.bbox ?? []);
  const caption = `${node.filename} p.${node.page}`;
  return (
    <>
      <button
        onClick={() => setLightbox({ url: imgUrl, caption })}
        className="group flex items-center gap-1.5 px-2 py-1 rounded-md bg-teal-50 dark:bg-teal-900/30 border border-teal-100 dark:border-teal-800 hover:bg-teal-100 dark:hover:bg-teal-900/60 transition-colors"
        title={caption}
      >
        <MapPin size={10} className="text-teal-500 shrink-0" />
        <span className="text-[11px] font-mono text-teal-700 dark:text-teal-300 truncate max-w-[140px]">
          {node.filename!.replace(/\.pdf$/i, "")} p.{node.page}
        </span>
        <span className="relative shrink-0 w-8 h-8 rounded overflow-hidden border border-teal-200 dark:border-teal-700 bg-white dark:bg-neutral-900">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imgUrl} alt="" className="w-full h-full object-cover" loading="lazy" />
        </span>
      </button>
      {lightbox && <Lightbox url={lightbox.url} caption={lightbox.caption} onClose={() => setLightbox(null)} />}
    </>
  );
}

// --- Topic group card ---
function TopicGroup({
  topic,
  facts,
  sourcesByFact,
}: {
  topic: CanvasNodeData;
  facts: CanvasNodeData[];
  sourcesByFact: Map<string, CanvasNodeData[]>;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const totalSources = facts.reduce((n, f) => n + (sourcesByFact.get(f.id) ?? []).length, 0);

  return (
    <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      {/* Topic header */}
      <button
        className="w-full flex items-center gap-2.5 px-4 py-3 bg-amber-50 dark:bg-amber-950/30 hover:bg-amber-100 dark:hover:bg-amber-900/40 transition-colors"
        onClick={() => setCollapsed((c) => !c)}
      >
        <Tag size={14} className="text-amber-600 dark:text-amber-400 shrink-0" />
        <span className="flex-1 text-left text-sm font-bold text-amber-900 dark:text-amber-100">
          {topic.title}
        </span>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/50 px-2 py-0.5 rounded-full">
            {facts.length} fact{facts.length !== 1 ? "s" : ""}
          </span>
          {totalSources > 0 && (
            <span className="text-[11px] text-teal-600 dark:text-teal-400 bg-teal-50 dark:bg-teal-900/30 px-2 py-0.5 rounded-full">
              {totalSources} src
            </span>
          )}
          {collapsed ? <ChevronRight size={14} className="text-amber-500" /> : <ChevronDown size={14} className="text-amber-500" />}
        </div>
      </button>

      {/* Facts list */}
      {!collapsed && (
        <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
          {facts.length === 0 ? (
            <p className="px-4 py-3 text-xs text-neutral-400 italic">No facts yet.</p>
          ) : (
            facts.map((fact, fi) => {
              const sources = sourcesByFact.get(fact.id) ?? [];
              return (
                <div key={fact.id} className="px-4 py-3 space-y-2">
                  <div className="flex items-start gap-2">
                    <MessageSquare size={12} className="text-indigo-400 shrink-0 mt-0.5" />
                    <p className="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed flex-1">
                      {fact.text}
                    </p>
                  </div>
                  {sources.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pl-5">
                      {sources.map((src) => <SourceChip key={src.id} node={src} />)}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

// --- Empty state ---
function EmptyFacts() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="h-16 w-16 rounded-2xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center mb-4">
        <FileText size={28} className="text-neutral-400 dark:text-neutral-500" />
      </div>
      <h3 className="text-base font-semibold text-neutral-700 dark:text-neutral-300 mb-1">No facts yet</h3>
      <p className="text-sm text-neutral-400 dark:text-neutral-500 max-w-xs">
        Ask a technical question — the agent will populate topics, facts, and sources here.
      </p>
    </div>
  );
}

// --- Main export ---
export function CanvasView({ canvas }: { canvas: CanvasState | null | undefined }) {
  const nodes = canvas?.nodes ?? [];
  const relations = canvas?.relations ?? [];

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Build children relationships
  const childrenOf = new Map<string, string[]>();
  for (const r of relations) {
    const arr = childrenOf.get(r.from_id) ?? [];
    arr.push(r.to_id);
    childrenOf.set(r.from_id, arr);
  }

  const topics = nodes.filter((n) => n.node_type === "topic");

  // For each topic, find its fact children
  const topicFacts = new Map<string, CanvasNodeData[]>();
  for (const topic of topics) {
    const factIds = (childrenOf.get(topic.id) ?? []).filter(
      (id) => nodeMap.get(id)?.node_type === "fact"
    );
    topicFacts.set(topic.id, factIds.map((id) => nodeMap.get(id)!).filter(Boolean));
  }

  // For each fact, find its source children
  const sourcesByFact = new Map<string, CanvasNodeData[]>();
  for (const n of nodes.filter((n) => n.node_type === "fact")) {
    const srcIds = (childrenOf.get(n.id) ?? []).filter(
      (id) => nodeMap.get(id)?.node_type === "source"
    );
    sourcesByFact.set(n.id, srcIds.map((id) => nodeMap.get(id)!).filter(Boolean));
  }

  if (topics.length === 0 && nodes.length === 0) return <EmptyFacts />;

  const topicCount = topics.length;
  const factCount = nodes.filter((n) => n.node_type === "fact").length;
  const srcCount = nodes.filter((n) => n.node_type === "source").length;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 px-1">
        <h2 className="text-sm font-semibold text-neutral-900 dark:text-white uppercase tracking-wider">Facts</h2>
        <span className="text-[11px] text-neutral-400 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded-full">
          {topicCount} topics · {factCount} facts · {srcCount} sources
        </span>
      </div>
      <div className="grid grid-cols-1 gap-4">
        {topics.map((topic) => (
          <TopicGroup
            key={topic.id}
            topic={topic}
            facts={topicFacts.get(topic.id) ?? []}
            sourcesByFact={sourcesByFact}
          />
        ))}
      </div>
    </div>
  );
}
