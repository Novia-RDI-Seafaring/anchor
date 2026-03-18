"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
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
  Box,
  FolderOpen,
  Loader2,
} from "lucide-react";
import type { KBDocument } from "@/contexts/AppContext";
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
  left_label?: string;
  left_value?: string;
  right_label?: string;
  right_value?: string;
  comparison_status?: string;
}

export interface CanvasNodeData {
  id: string;
  node_type: "topic" | "fact" | "spec" | "source" | "entity" | "category"; // source/entity/category kept for compat
  status?: NodeStatus;
  title?: string;
  text?: string;
  spec_title?: string;
  properties?: SpecProperty[];
}

export interface EvidenceRelation {
  from_id: string;
  to_id: string;  // __doc_{document_id}
  label: string;
  document_id: string;
  page: number;
  bbox: number[];
  highlights: PDFHighlight[];
}

export interface TopicNodeData {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
}

export interface FactNodeData {
  node: CanvasNodeData;
  onOpenPDF?: (filename: string, page: number, highlights: PDFHighlight[]) => void;
}

// SourceNodeData uses `any` for the node because source nodes are legacy/backward-compat
// and carry fields (filename, page, bbox, highlights) no longer in CanvasNodeData.
export interface SourceNodeData {
  node: any;
  onOpenPDF: (filename: string, page: number, highlights: PDFHighlight[]) => void;
}

export interface SpecNodeData {
  node: CanvasNodeData;
}

export interface EntityNodeData {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
}

export interface CategoryNodeData {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
}

// ─────────────────────────────────────────────
// ENTITY NODE — dark slate, the product/system root
// ─────────────────────────────────────────────
export function EntityNode({ data }: NodeProps) {
  const { node, childCount, collapsed, onToggleCollapse } = data as unknown as EntityNodeData;
  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-slate-500 !border-slate-700" />
      <div
        className={`rounded-2xl border-2 shadow-xl select-none transition-all ${
          collapsed
            ? "border-slate-500 dark:border-slate-400 bg-slate-700 dark:bg-slate-800"
            : "border-slate-600 dark:border-slate-400 bg-slate-800 dark:bg-slate-900"
        }`}
        style={{ minWidth: 200, maxWidth: 320 }}
      >
        <div className="flex items-center gap-2.5 px-4 py-3">
          <div className="shrink-0 w-7 h-7 rounded-lg bg-slate-600 dark:bg-slate-700 flex items-center justify-center">
            <Box size={14} className="text-slate-200" />
          </div>
          <p className="flex-1 text-sm font-extrabold text-white leading-snug tracking-tight break-words whitespace-normal">
            {node.title}
          </p>
          <StatusBadge status={node.status} />
          <button
            onClick={() => onToggleCollapse(node.id)}
            className="shrink-0 p-0.5 rounded hover:bg-slate-600 dark:hover:bg-slate-700 text-slate-300 transition-colors"
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? <ChevronsUpDown size={13} /> : <ChevronsDownUp size={13} />}
          </button>
        </div>
        {collapsed && childCount > 0 && (
          <div className="px-4 pb-2.5 -mt-1">
            <span className="text-[10px] text-slate-300 bg-slate-600/60 px-2 py-0.5 rounded-full">
              {childCount} hidden
            </span>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-500 !border-slate-700" />
    </>
  );
}

// ─────────────────────────────────────────────
// CATEGORY NODE — blue, chapter/section level
// ─────────────────────────────────────────────
export function CategoryNode({ data }: NodeProps) {
  const { node, childCount, collapsed, onToggleCollapse } = data as unknown as CategoryNodeData;
  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-blue-500 !border-blue-700" />
      <div
        className={`rounded-xl border-2 shadow-md select-none transition-all ${
          collapsed
            ? "border-blue-300 dark:border-blue-600 bg-blue-50 dark:bg-blue-950/40"
            : "border-blue-400 dark:border-blue-500 bg-blue-100 dark:bg-blue-900/30"
        }`}
        style={{ minWidth: 160, maxWidth: 280 }}
      >
        <div className="flex items-center gap-2 px-3 py-2.5">
          <FolderOpen size={14} className="text-blue-600 dark:text-blue-400 shrink-0" />
          <p className="flex-1 text-sm font-bold text-blue-900 dark:text-blue-100 leading-snug break-words whitespace-normal">
            {node.title}
          </p>
          <StatusBadge status={node.status} />
          <button
            onClick={() => onToggleCollapse(node.id)}
            className="shrink-0 p-0.5 rounded hover:bg-blue-200 dark:hover:bg-blue-800/60 text-blue-600 dark:text-blue-400 transition-colors"
            title={collapsed ? "Expand children" : "Collapse children"}
          >
            {collapsed ? <ChevronsUpDown size={13} /> : <ChevronsDownUp size={13} />}
          </button>
        </div>
        {collapsed && childCount > 0 && (
          <div className="px-3 pb-2 -mt-1">
            <span className="text-[10px] text-blue-600 dark:text-blue-400 bg-blue-200/60 dark:bg-blue-900/60 px-2 py-0.5 rounded-full">
              {childCount} hidden
            </span>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-blue-500 !border-blue-700" />
    </>
  );
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
  const { node } = data as unknown as FactNodeData;

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
          <div className={`flex-1 text-xs leading-relaxed break-words min-w-0 ${
            node.status === "pending" || node.status === "searching"
              ? "text-neutral-400 dark:text-neutral-500 italic"
              : "text-neutral-800 dark:text-neutral-200"
          } prose prose-xs dark:prose-invert max-w-none
            prose-p:my-0.5 prose-p:leading-relaxed
            prose-ul:my-0.5 prose-ul:pl-4
            prose-ol:my-0.5 prose-ol:pl-4
            prose-li:my-0
            prose-strong:font-semibold
            prose-headings:text-xs prose-headings:font-semibold prose-headings:my-1
            prose-code:text-[10px] prose-code:bg-neutral-100 dark:prose-code:bg-neutral-800 prose-code:px-1 prose-code:rounded
          `}>
            <ReactMarkdown>{node.text ?? ""}</ReactMarkdown>
          </div>
          <StatusBadge status={node.status} />
        </div>
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
  const isComparison = props.some((property) => property.left_value || property.right_value || property.comparison_status);
  const comparisonLeftLabel = props.find((property) => property.left_label)?.left_label || "Document A";
  const comparisonRightLabel = props.find((property) => property.right_label)?.right_label || "Document B";
  const comparisonTone = (status?: string) => {
    if (status === "same") return "text-emerald-700 bg-emerald-50 dark:text-emerald-300 dark:bg-emerald-950/40";
    if (status === "missing") return "text-amber-700 bg-amber-50 dark:text-amber-300 dark:bg-amber-950/40";
    return "text-rose-700 bg-rose-50 dark:text-rose-300 dark:bg-rose-950/40";
  };

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-violet-400 !border-violet-600" />
      <div
        className="rounded-lg border border-violet-200 dark:border-violet-700 bg-white dark:bg-neutral-900 shadow-sm overflow-hidden"
        style={{ borderLeft: "4px solid rgb(139 92 246)", minWidth: 180, maxWidth: isComparison ? 480 : 300 }}
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
              {isComparison && (
                <tr className="bg-violet-50/70 dark:bg-violet-950/30">
                  <td className="px-2.5 py-1 text-neutral-500 dark:text-neutral-400 font-semibold border-r border-violet-100 dark:border-violet-800/50">
                    Property
                  </td>
                  <td className="px-2.5 py-1 text-neutral-700 dark:text-neutral-200 font-semibold border-r border-violet-100 dark:border-violet-800/50">
                    {comparisonLeftLabel}
                  </td>
                  <td className="px-2.5 py-1 text-neutral-700 dark:text-neutral-200 font-semibold border-r border-violet-100 dark:border-violet-800/50">
                    {comparisonRightLabel}
                  </td>
                  <td className="px-2.5 py-1 text-neutral-500 dark:text-neutral-400 font-semibold">
                    Status
                  </td>
                </tr>
              )}
              {props.map((p, i) => (
                <tr
                  key={i}
                  className={i % 2 === 0 ? "bg-white dark:bg-neutral-900" : "bg-violet-50/50 dark:bg-violet-950/20"}
                >
                  <td className="px-2.5 py-1 text-neutral-500 dark:text-neutral-400 font-medium whitespace-nowrap border-r border-violet-100 dark:border-violet-800/50 max-w-[120px] truncate">
                    {p.key}
                  </td>
                  {isComparison ? (
                    <>
                      <td className="px-2.5 py-1 text-neutral-800 dark:text-neutral-200 font-mono border-r border-violet-100 dark:border-violet-800/50">
                        {p.left_value || "—"}
                      </td>
                      <td className="px-2.5 py-1 text-neutral-800 dark:text-neutral-200 font-mono border-r border-violet-100 dark:border-violet-800/50">
                        {p.right_value || "—"}
                      </td>
                      <td className="px-2.5 py-1">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${comparisonTone(p.comparison_status)}`}>
                          {p.comparison_status || "different"}
                        </span>
                      </td>
                    </>
                  ) : (
                    <td className="px-2.5 py-1 text-neutral-800 dark:text-neutral-200 font-mono">
                      {p.value}{p.unit ? <span className="text-neutral-400 ml-1">{p.unit}</span> : null}
                    </td>
                  )}
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

// ─── Document Node ─────────────────────────────────────────────────────────
export interface DocumentNodeData extends Record<string, unknown> {
  doc: KBDocument;
  isActive: boolean;
  onActivate: (id: string) => void;
  onOpenPDF: (filename: string, page: number, highlights: PDFHighlight[]) => void;
  evidenceCount: number;
}

export function DocumentNode({ data }: NodeProps) {
  const { doc, isActive, onActivate, onOpenPDF, evidenceCount } = data as DocumentNodeData;
  const isProcessing = doc.status === "processing" || doc.status === "pending";
  const isError = doc.status === "error" || doc.status === "failed";
  const stem = doc.filename.replace(/\.[^.]+$/, "");

  return (
    <button
      onClick={() => {
        onActivate(isActive ? "" : doc.document_id);
        onOpenPDF(doc.filename, 1, []);
      }}
      title={doc.filename}
      className={`group flex flex-col gap-1 px-3 py-2.5 rounded-xl border-2 transition-all shadow-sm text-left cursor-pointer w-full ${
        isActive
          ? "border-indigo-400 dark:border-indigo-500 bg-indigo-50 dark:bg-indigo-950/50"
          : "border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 hover:border-indigo-300 dark:hover:border-indigo-600 hover:bg-indigo-50/40 dark:hover:bg-indigo-950/20"
      }`}
      style={{ minWidth: 140, maxWidth: 160 }}
    >
      <div className="flex items-center gap-2">
        <div className={`h-7 w-7 rounded-lg flex items-center justify-center shrink-0 ${
          isActive
            ? "bg-indigo-100 dark:bg-indigo-900"
            : "bg-neutral-100 dark:bg-neutral-800 group-hover:bg-indigo-100 dark:group-hover:bg-indigo-900/50"
        }`}>
          {isProcessing ? (
            <Loader2 size={14} className="animate-spin text-amber-500" />
          ) : isError ? (
            <XCircle size={14} className="text-red-500" />
          ) : (
            <FileText size={14} className={isActive ? "text-indigo-600 dark:text-indigo-400" : "text-neutral-500 dark:text-neutral-400"} />
          )}
        </div>
        <span className={`text-[11px] font-medium truncate leading-tight ${
          isActive ? "text-indigo-700 dark:text-indigo-300" : "text-neutral-700 dark:text-neutral-300"
        }`}>
          {stem}
        </span>
      </div>
      <div className="flex items-center gap-1.5 pl-0.5">
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
          isProcessing
            ? "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400"
            : isError
            ? "bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400"
            : "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400"
        }`}>
          {isProcessing ? "processing" : isError ? "error" : `${doc.node_count} chunks`}
        </span>
        {evidenceCount > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-100 dark:bg-teal-900/40 text-teal-700 dark:text-teal-300">
            {evidenceCount} ref{evidenceCount !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </button>
  );
}
