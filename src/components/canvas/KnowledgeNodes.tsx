"use client";

import React, { useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Tag,
  MessageSquare,
  FileText,
  ChevronDown,
  ChevronUp,
  ChevronsDownUp,
  ChevronsUpDown,
  Table2,
  CheckCircle2,
  XCircle,
  CircleDashed,
  CircleAlert,
} from "lucide-react";
import type { PDFHighlight } from "./PDFModal";

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

// --- Status badge ---
type NodeStatus = "pending" | "searching" | "found" | "partial" | "not_found";

function StatusBadge({ status }: { status?: NodeStatus }) {
  if (!status || status === "found") {
    return <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />;
  }
  if (status === "pending") {
    return (
      <span className="shrink-0 inline-block w-3 h-3 rounded-full bg-amber-400 animate-pulse" />
    );
  }
  if (status === "searching") {
    return (
      <span className="shrink-0 inline-block w-3 h-3 rounded-full bg-blue-400 animate-ping" />
    );
  }
  if (status === "partial") {
    return <CircleAlert size={12} className="text-orange-400 shrink-0" />;
  }
  if (status === "not_found") {
    return <XCircle size={12} className="text-red-500 shrink-0" />;
  }
  return <CircleDashed size={12} className="text-neutral-400 shrink-0" />;
}

// --- Shared types (mirror backend CanvasNode) ---
export interface SpecProperty {
  key: string;
  value: string;
  unit?: string;
}

export interface CanvasNodeData {
  id: string;
  node_type: "topic" | "fact" | "source" | "spec";
  status?: NodeStatus;
  title?: string;
  text?: string;
  filename?: string;
  page?: number;
  bbox?: number[];
  highlights?: PDFHighlight[]; // ordered list of page+bbox refs for this source
  spec_title?: string;
  properties?: SpecProperty[];
}

export interface TopicNodeData {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
}

export interface FactNodeData {
  node: CanvasNodeData;
  // Source nodes directly connected to this fact (pre-computed in graph)
  sources: CanvasNodeData[];
  onOpenPDF: (filename: string, page: number, highlights: PDFHighlight[]) => void;
}

export interface SourceNodeData {
  node: CanvasNodeData;
  onOpenPDF: (filename: string, page: number, highlights: PDFHighlight[]) => void;
}

export interface SpecNodeData {
  node: CanvasNodeData;
}

// --- URL helpers ---
function bboxUrl(filename: string, page: number, bbox: number[]): string {
  const [l = 0, t = 0, r = 0, b = 0] = bbox;
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}&bbox_l=${l}&bbox_t=${t}&bbox_r=${r}&bbox_b=${b}`;
}

// ─────────────────────────────────────────────
// TOPIC NODE — amber, collapsible
// ─────────────────────────────────────────────
export function TopicNode({ data }: NodeProps) {
  const { node, childCount, collapsed, onToggleCollapse } = data as unknown as TopicNodeData;
  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-amber-400 !border-amber-600" />
      <div
        className={`rounded-xl border-2 shadow-md min-w-[180px] max-w-[260px] select-none transition-all ${
          collapsed
            ? "border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-950/40"
            : "border-amber-400 dark:border-amber-500 bg-amber-100 dark:bg-amber-900/30"
        }`}
      >
        <div className="flex items-start gap-2 px-3 py-2.5">
          <Tag size={14} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <p className="flex-1 text-sm font-bold text-amber-900 dark:text-amber-100 leading-snug break-words whitespace-normal">
            {node.title}
          </p>
          <StatusBadge status={node.status} />
          <button
            onClick={() => onToggleCollapse(node.id)}
            className="shrink-0 p-0.5 rounded hover:bg-amber-200 dark:hover:bg-amber-800/60 text-amber-600 dark:text-amber-400 transition-colors"
            title={collapsed ? "Expand children" : "Collapse children"}
          >
            {collapsed ? <ChevronsUpDown size={13} /> : <ChevronsDownUp size={13} />}
          </button>
        </div>
        {collapsed && childCount > 0 && (
          <div className="px-3 pb-2 -mt-1">
            <span className="text-[10px] text-amber-600 dark:text-amber-400 bg-amber-200/60 dark:bg-amber-900/60 px-2 py-0.5 rounded-full">
              {childCount} hidden
            </span>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-amber-400 !border-amber-600" />
    </>
  );
}

// ─────────────────────────────────────────────
// FACT NODE — indigo left-border, full text
// ─────────────────────────────────────────────
export function FactNode({ data }: NodeProps) {
  const { node, sources, onOpenPDF } = data as unknown as FactNodeData;
  const [expanded, setExpanded] = useState(false);

  const allHighlights: PDFHighlight[] = sources.map((s) => ({
    page: s.page ?? 1,
    bbox: s.bbox ?? [],
  }));

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-indigo-400 !border-indigo-600" />
      <div
        className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow-sm"
        style={{
          borderLeft: "4px solid rgb(99 102 241)",
          minWidth: 180,
          maxWidth: 280,
        }}
      >
        {/* Text row */}
        <div className="flex items-start gap-2 px-3 py-2.5">
          <MessageSquare size={13} className="text-indigo-400 dark:text-indigo-500 shrink-0 mt-0.5" />
          <p className={`flex-1 text-xs leading-relaxed break-words whitespace-normal ${
            node.status === "pending" || node.status === "searching"
              ? "text-neutral-400 dark:text-neutral-500 italic"
              : "text-neutral-800 dark:text-neutral-200"
          }`}>
            {node.text}
          </p>
          <StatusBadge status={node.status} />
          {sources.length > 0 && (
            <button
              onClick={() => setExpanded((e) => !e)}
              className="shrink-0 p-0.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-400 transition-colors"
              title={expanded ? "Hide sources" : "Show source screenshots"}
            >
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
          )}
        </div>

        {/* Expanded: bbox screenshot thumbnails */}
        {expanded && sources.length > 0 && (
          <div className="border-t border-neutral-100 dark:border-neutral-800 px-2.5 pb-2.5 pt-2 flex flex-wrap gap-2">
            {sources.map((src, i) => {
              if (!src.filename) return null;
              const imgUrl = bboxUrl(src.filename, src.page ?? 1, src.bbox ?? []);
              return (
                <button
                  key={i}
                  onClick={() => onOpenPDF(src.filename!, src.page ?? 1, allHighlights)}
                  className="group relative w-20 h-14 rounded overflow-hidden border-2 border-indigo-200 dark:border-indigo-700 hover:border-indigo-400 transition-colors shadow-sm"
                  title={`${src.filename} p.${src.page} — open PDF`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={imgUrl}
                    alt=""
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                    loading="lazy"
                  />
                  <div className="absolute bottom-0.5 right-0.5 bg-black/60 rounded px-1 py-0.5 flex items-center gap-0.5">
                    <FileText size={7} className="text-white" />
                    <span className="text-[8px] text-white font-mono">{src.page}</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-400 !border-indigo-600" />
    </>
  );
}

// ─────────────────────────────────────────────
// SPEC NODE — violet, two-column property table
// ─────────────────────────────────────────────
export function SpecNode({ data }: NodeProps) {
  const { node } = data as unknown as SpecNodeData;
  const props = node.properties ?? [];

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-violet-400 !border-violet-600" />
      <div
        className="rounded-lg border border-violet-200 dark:border-violet-700 bg-white dark:bg-neutral-900 shadow-sm overflow-hidden"
        style={{ borderLeft: "4px solid rgb(139 92 246)", minWidth: 180, maxWidth: 300 }}
      >
        {/* Header */}
        <div className="flex items-center gap-1.5 px-3 py-2 bg-violet-50 dark:bg-violet-950/40 border-b border-violet-100 dark:border-violet-800">
          <Table2 size={12} className="text-violet-500 shrink-0" />
          <span className="flex-1 text-xs font-semibold text-violet-800 dark:text-violet-200 truncate">
            {node.spec_title || "Specifications"}
          </span>
          <StatusBadge status={node.status} />
        </div>
        {/* Property rows */}
        {props.length > 0 ? (
          <table className="w-full text-[11px] border-collapse">
            <tbody>
              {props.map((p, i) => (
                <tr
                  key={i}
                  className={i % 2 === 0 ? "bg-white dark:bg-neutral-900" : "bg-violet-50/50 dark:bg-violet-950/20"}
                >
                  <td className="px-2.5 py-1 text-neutral-500 dark:text-neutral-400 font-medium whitespace-nowrap border-r border-violet-100 dark:border-violet-800/50 max-w-[120px] truncate">
                    {p.key}
                  </td>
                  <td className="px-2.5 py-1 text-neutral-800 dark:text-neutral-200 font-mono">
                    {p.value}{p.unit ? <span className="text-neutral-400 ml-1">{p.unit}</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : node.status === "pending" || node.status === "searching" ? (
          <p className="px-3 py-2.5 text-[11px] text-violet-400 dark:text-violet-500 italic">
            {node.status === "searching" ? "Extracting data…" : "Waiting to search…"}
          </p>
        ) : (
          <p className="px-3 py-2 text-xs text-neutral-400 italic">No properties</p>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-violet-400 !border-violet-600" />
    </>
  );
}

// ─────────────────────────────────────────────
// SOURCE NODE — teal, opens PDF on click
// ─────────────────────────────────────────────
export function SourceNode({ data }: NodeProps) {
  const { node, onOpenPDF } = data as unknown as SourceNodeData;
  const short = (node.filename ?? "").replace(/\.pdf$/i, "").slice(0, 20);

  // Resolve highlights: use node.highlights if present, otherwise build from page+bbox
  const highlights: PDFHighlight[] =
    node.highlights && node.highlights.length > 0
      ? node.highlights
      : node.page ? [{ page: node.page, bbox: node.bbox ?? [] }] : [];

  const hlCount = highlights.length;

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-teal-400 !border-teal-600" />
      <button
        onClick={() => onOpenPDF(node.filename!, highlights[0]?.page ?? node.page ?? 1, highlights)}
        className="group flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border-2 border-teal-200 dark:border-teal-700 bg-teal-50 dark:bg-teal-950/40 hover:border-teal-400 dark:hover:border-teal-500 hover:bg-teal-100 dark:hover:bg-teal-900/40 transition-all shadow-sm"
        style={{ minWidth: 100, maxWidth: 180 }}
        title={`${node.filename} — ${hlCount} highlight${hlCount !== 1 ? "s" : ""} — click to open PDF`}
      >
        <FileText size={12} className="text-teal-600 dark:text-teal-400 shrink-0" />
        <span className="text-[11px] font-mono text-teal-800 dark:text-teal-200 truncate">
          {short}
        </span>
        {hlCount > 1 ? (
          <span className="shrink-0 text-[10px] bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded-full font-mono">
            {hlCount}×
          </span>
        ) : (
          <span className="shrink-0 text-[10px] bg-teal-200 dark:bg-teal-800 text-teal-700 dark:text-teal-300 px-1.5 py-0.5 rounded-full font-mono">
            p.{highlights[0]?.page ?? node.page}
          </span>
        )}
      </button>
    </>
  );
}
