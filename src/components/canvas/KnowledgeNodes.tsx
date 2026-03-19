"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Handle, Position, NodeToolbar, type NodeProps } from "@xyflow/react";
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
  Layers,
  Cpu,
  Activity,
  Play,
} from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { KBDocument } from "@/contexts/AppContext";
import type { PDFHighlight } from "./PDFModal";

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

// --- Shared delete toolbar (appears when node is selected) ---
function DeleteToolbar({ nodeId, onDelete }: { nodeId: string; onDelete?: (id: string) => void }) {
  if (!onDelete) return null;
  return (
    <NodeToolbar isVisible={undefined} position={Position.Top} align="end" offset={6}>
      <button
        onClick={() => onDelete(nodeId)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-white dark:bg-neutral-800 border border-red-200 dark:border-red-700 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 shadow-md transition-colors"
        title="Delete node"
      >
        <XCircle size={14} />
        Delete
      </button>
    </NodeToolbar>
  );
}

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

export interface FmuVariableData {
  name: string;
  causality: string;
  variability?: string;
  start?: string;
  unit?: string;
  description?: string;
}

export interface CanvasNodeData {
  id: string;
  node_type: "concept" | "topic" | "fact" | "spec" | "source" | "entity" | "category" | "fmu" | "plot"; // source/entity/category kept for compat
  status?: NodeStatus;
  title?: string;
  text?: string;
  spec_title?: string;
  properties?: SpecProperty[];
  // fmu node fields
  fmu_filename?: string;
  fmu_model_name?: string;
  fmu_variables?: FmuVariableData[];
  fmu_param_values?: Record<string, string>;
  // plot node fields
  plot_job_id?: string;
  plot_fmu_filename?: string;
  plot_signal_names?: string[];
  plot_stop_time?: number;
  plot_param_values?: Record<string, number>;
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
  onDelete?: (id: string) => void;
}

export interface FactNodeData {
  node: CanvasNodeData;
  onOpenPDF?: (filename: string, page: number, highlights: PDFHighlight[]) => void;
  onDelete?: (id: string) => void;
  evidenceFilename?: string;
  evidencePage?: number;
  evidenceHighlights?: PDFHighlight[];
}

// SourceNodeData uses `any` for the node because source nodes are legacy/backward-compat
// and carry fields (filename, page, bbox, highlights) no longer in CanvasNodeData.
export interface SourceNodeData {
  node: any;
  onOpenPDF: (filename: string, page: number, highlights: PDFHighlight[]) => void;
}

export interface SpecNodeData {
  node: CanvasNodeData;
  onOpenPDF?: (filename: string, page: number, highlights: PDFHighlight[]) => void;
  onDelete?: (id: string) => void;
  evidenceFilename?: string;
  evidencePage?: number;
  evidenceHighlights?: PDFHighlight[];
}

export interface EntityNodeData {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
  onDelete?: (id: string) => void;
}

export interface CategoryNodeData {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
  onDelete?: (id: string) => void;
}

export interface ConceptNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
  onDelete?: (id: string) => void;
}

// ─────────────────────────────────────────────
// ENTITY NODE — dark slate, the product/system root
// ─────────────────────────────────────────────
export function EntityNode({ data }: NodeProps) {
  const { node, childCount, collapsed, onToggleCollapse, onDelete } = data as unknown as EntityNodeData;
  return (
    <>
      <DeleteToolbar nodeId={node.id} onDelete={onDelete} />
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
  const { node, childCount, collapsed, onToggleCollapse, onDelete } = data as unknown as CategoryNodeData;
  return (
    <>
      <DeleteToolbar nodeId={node.id} onDelete={onDelete} />
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
// CONCEPT NODE — violet, subject-level root
// ─────────────────────────────────────────────
export function ConceptNode({ data }: NodeProps) {
  const { node, childCount, collapsed, onToggleCollapse, onDelete } = data as unknown as ConceptNodeData;
  return (
    <>
      <DeleteToolbar nodeId={node.id} onDelete={onDelete} />
      <Handle type="target" position={Position.Top} className="!bg-violet-500 !border-violet-700" />
      <div
        className={`rounded-xl border-2 shadow-lg select-none transition-all ${
          collapsed
            ? "border-violet-300 dark:border-violet-600 bg-violet-50 dark:bg-violet-950/40"
            : "border-violet-500 dark:border-violet-400 bg-violet-100 dark:bg-violet-900/30"
        }`}
        style={{ minWidth: 180, maxWidth: 300 }}
      >
        <div className="flex items-center gap-2 px-3 py-2.5">
          <Layers size={14} className="text-violet-600 dark:text-violet-400 shrink-0" />
          <p className="flex-1 text-sm font-bold text-violet-900 dark:text-violet-100 leading-snug break-words whitespace-normal">
            {node.title}
          </p>
          <StatusBadge status={node.status} />
          <button
            onClick={() => onToggleCollapse(node.id)}
            className="shrink-0 p-0.5 rounded hover:bg-violet-200 dark:hover:bg-violet-800/60 text-violet-600 dark:text-violet-400 transition-colors"
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? <ChevronsUpDown size={13} /> : <ChevronsDownUp size={13} />}
          </button>
        </div>
        {collapsed && childCount > 0 && (
          <div className="px-3 pb-2 -mt-1">
            <span className="text-[10px] text-violet-600 dark:text-violet-400 bg-violet-200/60 dark:bg-violet-900/60 px-2 py-0.5 rounded-full">
              {childCount} hidden
            </span>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-violet-500 !border-violet-700" />
    </>
  );
}

// ─────────────────────────────────────────────
// TOPIC NODE — amber, collapsible
// ─────────────────────────────────────────────
export function TopicNode({ data }: NodeProps) {
  const { node, childCount, collapsed, onToggleCollapse, onDelete } = data as unknown as TopicNodeData;
  return (
    <>
      <DeleteToolbar nodeId={node.id} onDelete={onDelete} />
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
  const { node, onDelete, onOpenPDF, evidenceFilename, evidencePage, evidenceHighlights } = data as unknown as FactNodeData;
  const hasEvidence = evidenceFilename && evidencePage !== undefined;

  return (
    <>
      <DeleteToolbar nodeId={node.id} onDelete={onDelete} />
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
        {/* Evidence link */}
        {hasEvidence && (
          <div className="px-3 pb-2 -mt-0.5">
            <button
              onClick={() => onOpenPDF?.(evidenceFilename!, evidencePage!, evidenceHighlights ?? [])}
              className="flex items-center gap-1 text-[10px] text-indigo-500 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
              title={`Open source — page ${evidencePage}`}
            >
              <FileText size={11} className="shrink-0" />
              <span>p.{evidencePage}</span>
            </button>
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
  const { node, onDelete, onOpenPDF, evidenceFilename, evidencePage, evidenceHighlights } = data as unknown as SpecNodeData;
  const hasEvidence = evidenceFilename && evidencePage !== undefined;
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
      <DeleteToolbar nodeId={node.id} onDelete={onDelete} />
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
          {hasEvidence && (
            <button
              onClick={() => onOpenPDF?.(evidenceFilename!, evidencePage!, evidenceHighlights ?? [])}
              className="flex items-center gap-0.5 text-[10px] text-violet-500 dark:text-violet-400 hover:text-violet-700 dark:hover:text-violet-300 transition-colors mr-1"
              title={`Open source — page ${evidencePage}`}
            >
              <FileText size={11} className="shrink-0" />
              <span>p.{evidencePage}</span>
            </button>
          )}
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

// ─────────────────────────────────────────────
// FMU NODE — teal, shows inputs/outputs/params
// ─────────────────────────────────────────────
export interface FmuNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onSimulate: (nodeId: string, filename: string, paramValues: Record<string, string>, stopTime: number) => void;
  onDelete?: (id: string) => void;
}

export interface PlotNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (nodeId: string) => void;
}

export function FmuNode({ data }: NodeProps) {
  const { node, onSimulate, onDelete } = data as unknown as FmuNodeData;
  const [paramValues, setParamValues] = React.useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    (node.fmu_variables ?? []).filter((v: FmuVariableData) => v.causality === 'parameter').forEach((v: FmuVariableData) => {
      init[v.name] = node.fmu_param_values?.[v.name] ?? v.start ?? '';
    });
    return init;
  });
  const [stopTime, setStopTime] = React.useState(node.plot_stop_time ?? 10);
  const inputs = (node.fmu_variables ?? []).filter((v: FmuVariableData) => v.causality === 'input');
  const outputs = (node.fmu_variables ?? []).filter((v: FmuVariableData) => v.causality === 'output');
  const params = (node.fmu_variables ?? []).filter((v: FmuVariableData) => v.causality === 'parameter');

  return (
    <>
      <DeleteToolbar nodeId={node.id} onDelete={onDelete} />
      <Handle type="target" position={Position.Top} className="!bg-teal-500 !border-teal-700" />
      <div className="rounded-xl border-2 border-teal-400 dark:border-teal-500 bg-teal-50 dark:bg-teal-950/40 shadow-md select-none" style={{ minWidth: 220, maxWidth: 320 }}>
        {/* Header */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-teal-200 dark:border-teal-800">
          <Cpu size={14} className="text-teal-600 dark:text-teal-400 shrink-0" />
          <span className="flex-1 text-sm font-bold text-teal-900 dark:text-teal-100 truncate">{node.fmu_model_name || node.title}</span>
          <span className="text-[9px] text-teal-500 font-mono bg-teal-100 dark:bg-teal-900 px-1.5 py-0.5 rounded">.fmu</span>
        </div>
        {/* Inputs */}
        {inputs.length > 0 && (
          <div className="px-3 py-1.5 border-b border-teal-100 dark:border-teal-900">
            <p className="text-[9px] font-semibold text-teal-500 uppercase tracking-wide mb-1">Inputs</p>
            {inputs.map((v: FmuVariableData) => (
              <div key={v.name} className="relative flex items-center gap-1 text-xs text-teal-800 dark:text-teal-200 py-0.5">
                <Handle type="target" id={`in-${v.name}`} position={Position.Left} className="!bg-teal-400 !w-2 !h-2 !border-teal-600" style={{ left: -8 }} />
                <span className="font-mono text-[10px]">{v.name}</span>
                {v.unit && <span className="text-[9px] text-teal-400 ml-1">[{v.unit}]</span>}
              </div>
            ))}
          </div>
        )}
        {/* Outputs */}
        {outputs.length > 0 && (
          <div className="px-3 py-1.5 border-b border-teal-100 dark:border-teal-900">
            <p className="text-[9px] font-semibold text-teal-500 uppercase tracking-wide mb-1">Outputs</p>
            {outputs.map((v: FmuVariableData) => (
              <div key={v.name} className="relative flex items-center justify-end gap-1 text-xs text-teal-800 dark:text-teal-200 py-0.5">
                <span className="font-mono text-[10px]">{v.name}</span>
                {v.unit && <span className="text-[9px] text-teal-400 mr-1">[{v.unit}]</span>}
                <Handle type="source" id={`out-${v.name}`} position={Position.Right} className="!bg-teal-400 !w-2 !h-2 !border-teal-600" style={{ right: -8 }} />
              </div>
            ))}
          </div>
        )}
        {/* Parameters */}
        {params.length > 0 && (
          <div className="px-3 py-1.5 border-b border-teal-100 dark:border-teal-900">
            <p className="text-[9px] font-semibold text-teal-500 uppercase tracking-wide mb-1">Parameters</p>
            {params.map((v: FmuVariableData) => (
              <div key={v.name} className="flex items-center gap-2 py-0.5">
                <span className="font-mono text-[10px] text-teal-700 dark:text-teal-300 w-20 truncate">{v.name}</span>
                <input
                  type="text"
                  value={paramValues[v.name] ?? ''}
                  onChange={e => setParamValues(prev => ({ ...prev, [v.name]: e.target.value }))}
                  className="nodrag flex-1 text-[10px] font-mono bg-white dark:bg-teal-900/40 border border-teal-200 dark:border-teal-700 rounded px-1.5 py-0.5 text-teal-900 dark:text-teal-100 w-0 min-w-0"
                />
                {v.unit && <span className="text-[9px] text-teal-400 shrink-0">{v.unit}</span>}
              </div>
            ))}
          </div>
        )}
        {/* Simulate controls */}
        <div className="px-3 py-2 flex items-center gap-2">
          <span className="text-[9px] text-teal-500">stop</span>
          <input
            type="number"
            value={stopTime}
            onChange={e => setStopTime(Number(e.target.value))}
            className="nodrag w-16 text-[10px] font-mono bg-white dark:bg-teal-900/40 border border-teal-200 dark:border-teal-700 rounded px-1.5 py-0.5 text-teal-900 dark:text-teal-100"
          />
          <span className="text-[9px] text-teal-500">s</span>
          <button
            onClick={() => onSimulate?.(node.id, node.fmu_filename ?? '', paramValues, stopTime)}
            className="nodrag ml-auto flex items-center gap-1 px-2.5 py-1 rounded-lg bg-teal-500 hover:bg-teal-600 text-white text-[11px] font-semibold transition-colors shadow-sm"
          >
            <Play size={10} />
            Simulate
          </button>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-teal-500 !border-teal-700" />
    </>
  );
}

// ─────────────────────────────────────────────
// PLOT NODE — shows simulation time-series
// ─────────────────────────────────────────────
export function PlotNode({ data }: NodeProps) {
  const { node, onDelete } = data as unknown as PlotNodeData;
  const [chartData, setChartData] = React.useState<Record<string, unknown>[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!node.plot_job_id) return;
    fetch(`${API_URL}/api/fmu/result/${node.plot_job_id}`)
      .then(r => r.ok ? r.json() : Promise.reject('not found'))
      .then((raw: Record<string, unknown>) => {
        const times: number[] = (raw.time as number[]) ?? [];
        const signals = Object.keys(raw).filter(k => k !== 'time');
        setChartData(times.map((t, i) => {
          const pt: Record<string, unknown> = { t: Math.round(t * 1000) / 1000 };
          signals.forEach(s => { pt[s] = (raw[s] as number[])[i]; });
          return pt;
        }));
      })
      .catch(() => setError('Could not load result'));
  }, [node.plot_job_id]);

  const signals = node.plot_signal_names ?? [];
  const params = node.plot_param_values ? Object.entries(node.plot_param_values) : [];
  const COLORS = ['#14b8a6', '#6366f1', '#f59e0b', '#ef4444', '#8b5cf6'];

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-indigo-400 !border-indigo-600" />
      <div className="rounded-xl border-2 border-indigo-300 dark:border-indigo-600 bg-white dark:bg-neutral-900 shadow-md" style={{ minWidth: 280, maxWidth: 400 }}>
        <div className="flex items-center gap-2 px-3 py-2 border-b border-neutral-100 dark:border-neutral-800">
          <Activity size={13} className="text-indigo-500 shrink-0" />
          <span className="flex-1 text-xs font-semibold text-neutral-800 dark:text-neutral-200 truncate">{node.title}</span>
          {node.plot_stop_time && <span className="text-[9px] text-neutral-400 font-mono">0–{node.plot_stop_time}s</span>}
          {onDelete && (
            <button
              onClick={() => onDelete(node.id)}
              className="ml-1 text-neutral-400 hover:text-red-500 dark:text-neutral-500 dark:hover:text-red-400 transition-colors"
              title="Delete result"
            >
              <XCircle size={16} />
            </button>
          )}
        </div>
        {params.length > 0 && (
          <div className="flex flex-wrap gap-1 px-3 py-1.5 border-b border-neutral-100 dark:border-neutral-800">
            {params.map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-1 text-[9px] font-mono bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-300 rounded px-1.5 py-0.5">
                <span className="font-semibold">{k}</span>
                <span className="text-indigo-400">=</span>
                <span>{v}</span>
              </span>
            ))}
          </div>
        )}
        <div className="p-2">
          {!node.plot_job_id && <p className="text-xs text-neutral-400 text-center py-4">No simulation yet</p>}
          {node.plot_job_id && !chartData && !error && <p className="text-xs text-neutral-400 text-center py-4">Loading…</p>}
          {error && <p className="text-xs text-red-400 text-center py-4">{error}</p>}
          {chartData && (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                <XAxis dataKey="t" tick={{ fontSize: 9 }} tickLine={false} />
                <YAxis tick={{ fontSize: 9 }} tickLine={false} width={40} />
                <Tooltip contentStyle={{ fontSize: 10 }} />
                {signals.map((s, i) => (
                  <Line key={s} type="monotone" dataKey={s} stroke={COLORS[i % COLORS.length]} dot={false} strokeWidth={1.5} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-400 !border-indigo-600" />
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
