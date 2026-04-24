"use client";

import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
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
  Image,
  Filter,
  ChevronRight,
  ChevronLeft,
  GripVertical,
  X,
} from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { KBDocument } from "@/contexts/AppContext";
import type { PDFHighlight } from "./PDFModal";
import type {
  CanvasItem,
  FmuVariableData,
  NodeStatus,
  SpecProperty,
  ParameterSection,
} from "./canvas-model";

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

function nodeFrameStyle(node: CanvasNodeData, fallback: { w: number; h: number }): React.CSSProperties {
  return {
    width: node.width && node.width > 0 ? node.width : fallback.w,
    height: node.height && node.height > 0 ? node.height : fallback.h,
  };
}


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

// --- Shared types (frontend canvas model) ---
export type CanvasNodeData = CanvasItem;

export interface EvidenceRelation {
  from_id: string;
  to_id: string;  // __doc_{document_id}
  label: string;
  source_handle?: string;
  target_handle?: string;
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
  onSetColor?: (id: string, color: string) => void;
}

export interface FactNodeData {
  node: CanvasNodeData;
  onOpenPDF?: (filename: string, page: number, highlights: PDFHighlight[]) => void;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  onUseInChat?: () => void;
  onPreviewSource?: (filename: string | null, page?: number | null) => void;
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
  onSetColor?: (id: string, color: string) => void;
  onUseInChat?: () => void;
  onPreviewSource?: (filename: string | null, page?: number | null) => void;
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
  onSetColor?: (id: string, color: string) => void;
}

export interface CategoryNodeData {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
}

export interface ImageNodeData {
  node: CanvasNodeData;
  onOpenPDF?: (filename: string, page: number, highlights: PDFHighlight[]) => void;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  onUseInChat?: () => void;
}

export interface ConceptNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  childCount: number;
  collapsed: boolean;
  onToggleCollapse: (id: string) => void;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
}

// ─────────────────────────────────────────────
// ENTITY NODE — dark slate, the product/system root
// ─────────────────────────────────────────────
export function EntityNode({ data }: NodeProps) {
  const { node, childCount, collapsed, onToggleCollapse, onDelete, onSetColor } = data as unknown as EntityNodeData;
  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-slate-500 !border-slate-700" />
      <div
        className={`flex items-center justify-center rounded-full border-[3px] shadow-lg select-none transition-all ${
          collapsed
            ? "border-slate-500 dark:border-slate-400 bg-slate-100 dark:bg-slate-800"
            : "border-slate-600 dark:border-slate-400 bg-white dark:bg-neutral-900"
        }`}
        style={{ width: '100%', height: '100%' }}
      >
        <div className="flex max-w-[80%] flex-col items-center gap-2 text-center">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-200">
            <Box size={16} />
          </div>
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug break-words whitespace-normal">
            {node.title}
          </p>
        </div>
        <div className="absolute right-3 top-3 flex items-center gap-1.5">
          <StatusBadge status={node.status} />
          <button
            onClick={() => onToggleCollapse(node.id)}
            className="rounded-full bg-white/80 p-1 text-slate-500 shadow-sm transition-colors hover:bg-slate-100 dark:bg-neutral-800/90 dark:text-slate-300 dark:hover:bg-neutral-700"
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? <ChevronsUpDown size={13} /> : <ChevronsDownUp size={13} />}
          </button>
        </div>
        {collapsed && childCount > 0 && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2">
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600 dark:bg-slate-700 dark:text-slate-200">
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
  const { node, childCount, collapsed, onToggleCollapse, onDelete, onSetColor } = data as unknown as CategoryNodeData;
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
// IMAGE NODE — sky blue, shows a PDF page screenshot
// ─────────────────────────────────────────────
const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

function buildPageImageUrl(filename: string, page: number, bbox?: number[], highlights?: string[]): string {
  const params = new URLSearchParams({ filename, page_no: String(page) });
  if (bbox && bbox.length === 4) {
    params.set("bbox_l", String(bbox[0]));
    params.set("bbox_t", String(bbox[1]));
    params.set("bbox_r", String(bbox[2]));
    params.set("bbox_b", String(bbox[3]));
  }
  if (highlights && highlights.length > 0) {
    highlights.forEach(p => params.append("phrase", p));
  }
  return `${API_BASE}/api/documents/pdf/screenshot?${params.toString()}`;
}

export function ImageNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, onOpenPDF, onUseInChat } = data as unknown as ImageNodeData;
  const hasImage = !!(node.image_filename && node.image_page);
  // Prefer direct image_url (e.g. gold region SVG crop) over bbox screenshot
  const imageUrl = (node as any).image_url
    || (hasImage ? buildPageImageUrl(node.image_filename!, node.image_page!, node.image_bbox, node.image_highlights) : null);
  const pdfHighlights: PDFHighlight[] = [];

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-sky-400 !border-sky-600" />
      <div
        className="rounded-xl border border-sky-200 dark:border-sky-700 bg-white dark:bg-neutral-900 shadow-md overflow-hidden"
        style={{ minWidth: 200, maxWidth: 320 }}
      >
        {/* Header */}
        <div className="flex items-center gap-1.5 px-3 py-2 bg-sky-50 dark:bg-sky-950/40 border-b border-sky-100 dark:border-sky-800">
          <Image size={12} className="text-sky-500 shrink-0" />
          <span className="flex-1 text-xs font-semibold text-sky-800 dark:text-sky-200 truncate">
            {node.title || (hasImage ? `${node.image_filename} p.${node.image_page}` : "Image")}
          </span>
          {hasImage && (
            <button
              onClick={() => onOpenPDF?.(node.image_filename!, node.image_page!, pdfHighlights)}
              className="text-sky-400 hover:text-sky-600 dark:hover:text-sky-300 transition-colors"
              title="Open in PDF viewer"
            >
              <FileText size={11} />
            </button>
          )}
          <button
            onClick={() => onUseInChat?.()}
            className="text-sky-400 hover:text-sky-600 dark:hover:text-sky-300 transition-colors"
            title="Use this node as chat context"
          >
            <MessageSquare size={11} />
          </button>
          <StatusBadge status={node.status} />
        </div>
        {/* Screenshot */}
        {imageUrl && (
          <button
            onClick={() => onOpenPDF?.(node.image_filename!, node.image_page!, pdfHighlights)}
            className="block w-full"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageUrl}
              alt={node.title || "PDF page"}
              className="w-full object-contain max-h-52"
              loading="lazy"
            />
          </button>
        )}
        {node.image_caption && (
          <p className="px-3 py-2 text-[10px] text-neutral-500 dark:text-neutral-400 italic">
            {node.image_caption}
          </p>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-sky-400 !border-sky-600" />
    </>
  );
}

// ─────────────────────────────────────────────
// CONCEPT NODE — violet, subject-level root
// ─────────────────────────────────────────────
export function ConceptNode({ data }: NodeProps) {
  const { node, childCount, collapsed, onToggleCollapse, onDelete, onSetColor } = data as unknown as ConceptNodeData;
  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-violet-500 !border-violet-700" />
      <div
        className={`relative flex flex-col justify-between rounded-[28px] border-[3px] shadow-md select-none transition-all ${
          collapsed
            ? "border-violet-300 dark:border-violet-600 bg-violet-50 dark:bg-violet-950/30"
            : "border-violet-500 dark:border-violet-400 bg-white dark:bg-neutral-900"
        }`}
        style={{ width: '100%', height: '100%' }}
      >
        <div className="flex items-center gap-2 px-4 py-3">
          <Layers size={14} className="text-violet-600 dark:text-violet-400 shrink-0" />
          <p className="flex-1 text-sm font-semibold text-violet-900 dark:text-violet-100 leading-snug break-words whitespace-normal">
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
          <div className="px-4 pb-3">
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
  const { node, childCount, collapsed, onToggleCollapse, onDelete, onSetColor } = data as unknown as TopicNodeData;
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
  const { node, onDelete, onSetColor, onOpenPDF, onUseInChat, onPreviewSource, evidenceFilename, evidencePage, evidenceHighlights } = data as unknown as FactNodeData;
  const hasEvidence = evidenceFilename && evidencePage !== undefined;

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-indigo-400 !border-indigo-600" />
      <div
        className="relative rounded-[26px] border-[3px] border-amber-400 bg-white shadow-sm dark:border-amber-500 dark:bg-neutral-900"
        style={{ width: '100%', height: '100%' }}
      >
        <div className="absolute right-3 top-3 flex items-center gap-1.5">
          <button
            onClick={() => onUseInChat?.()}
            className="text-amber-500 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-200 transition-colors"
            title="Use this node as chat context"
          >
            <MessageSquare size={12} />
          </button>
          <StatusBadge status={node.status} />
        </div>
        {/* Text row */}
        <div className="flex h-full items-start gap-2 px-4 py-3">
          <MessageSquare size={13} className="text-amber-500 dark:text-amber-400 shrink-0 mt-0.5" />
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
        </div>
        {/* Evidence link */}
        {hasEvidence && (
          <div className="absolute bottom-3 left-4">
            <button
              onClick={() => onOpenPDF?.(evidenceFilename!, evidencePage!, evidenceHighlights ?? [])}
              onMouseEnter={() => onPreviewSource?.(evidenceFilename!, evidencePage!)}
              onMouseLeave={() => onPreviewSource?.(null, null)}
              className="flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-300 hover:text-amber-700 dark:hover:text-amber-200 transition-colors"
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
  const { node, onDelete, onSetColor, onOpenPDF, onUseInChat, onPreviewSource, evidenceFilename, evidencePage, evidenceHighlights } = data as unknown as SpecNodeData;
  const hasEvidence = evidenceFilename && evidencePage !== undefined;
  const sections: ParameterSection[] = (node as any).parameter_sections ?? [];
  const useSections = sections.length > 0;
  const props = node.properties ?? [];
  const isComparison = props.some((property) => property.left_value || property.right_value || property.comparison_status);
  const comparisonLeftLabel = props.find((property) => property.left_label)?.left_label || "Document A";
  const comparisonRightLabel = props.find((property) => property.right_label)?.right_label || "Document B";
  const comparisonTone = (status?: string) => {
    if (status === "same") return "text-emerald-700 bg-emerald-50 dark:text-emerald-300 dark:bg-emerald-950/40";
    if (status === "missing") return "text-amber-700 bg-amber-50 dark:text-amber-300 dark:bg-amber-950/40";
    return "text-rose-700 bg-rose-50 dark:text-rose-300 dark:bg-rose-950/40";
  };
  const propertyHighlights = (property: SpecProperty): PDFHighlight[] => {
    if (property.ref_highlights && property.ref_highlights.length > 0) return property.ref_highlights;
    if (property.ref_page) return [{ page: property.ref_page, bbox: property.ref_bbox ?? [] }];
    return [];
  };
  const rowInputHandleId = (sectionIndex: number, rowIndex: number) => `spec-row-in-${sectionIndex}-${rowIndex}`;
  const rowOutputHandleId = (sectionIndex: number, rowIndex: number) => `spec-row-out-${sectionIndex}-${rowIndex}`;
  const propertyInputHandleId = (propertyIndex: number) => `spec-prop-in-${propertyIndex}`;
  const propertyOutputHandleId = (propertyIndex: number) => `spec-prop-out-${propertyIndex}`;

  return (
    <div style={{ padding: "0 14px" }}>

      <Handle type="target" position={Position.Top} className="!bg-violet-400 !border-violet-600" />
      <div
        className="rounded-lg border border-violet-200 dark:border-violet-700 bg-white dark:bg-neutral-900 shadow-sm"
        style={{ borderLeft: "4px solid rgb(139 92 246)", minWidth: 240, maxWidth: 520 }}
      >
        {/* Header */}
        <div className="flex items-center gap-1.5 px-3 py-2 bg-violet-50 dark:bg-violet-950/40 border-b border-violet-100 dark:border-violet-800">
          <Table2 size={12} className="text-violet-500 shrink-0" />
          <span className="flex-1 text-xs font-semibold text-violet-800 dark:text-violet-200">
            {node.spec_title || "Specifications"}
          </span>
          {hasEvidence && (
            <button
              onClick={() => onOpenPDF?.(evidenceFilename!, evidencePage!, evidenceHighlights ?? [])}
              onMouseEnter={() => onPreviewSource?.(evidenceFilename!, evidencePage!)}
              onMouseLeave={() => onPreviewSource?.(null, null)}
              className="flex items-center gap-0.5 text-[10px] text-violet-500 dark:text-violet-400 hover:text-violet-700 dark:hover:text-violet-300 transition-colors mr-1"
              title={`Open source — page ${evidencePage}`}
            >
              <FileText size={11} className="shrink-0" />
              <span>p.{evidencePage}</span>
            </button>
          )}
          <button
            onClick={() => onUseInChat?.()}
            className="text-violet-500 dark:text-violet-400 hover:text-violet-700 dark:hover:text-violet-300 transition-colors mr-1"
            title="Use this node as chat context"
          >
            <MessageSquare size={11} />
          </button>
          <StatusBadge status={node.status} />
        </div>
        {/* Parameter sections (new structured format) */}
        {useSections ? (
          <table className="w-full text-[11px] border-collapse">
            <tbody>
              {sections.map((section, si) => (
                <React.Fragment key={si}>
                  <tr className="bg-violet-100/70 dark:bg-violet-900/30">
                    <td colSpan={4} className="px-2.5 py-1">
                      <div className="text-[10px] font-bold text-violet-700 dark:text-violet-300 uppercase tracking-wide truncate max-w-[280px]" title={section.name}>
                        {section.name}
                      </div>
                    </td>
                  </tr>
                  {section.rows.map((row, ri) => (
                    <tr key={ri} className={ri % 2 === 0 ? "bg-white dark:bg-neutral-900" : "bg-violet-50/50 dark:bg-violet-950/20"}>
                      <td className="relative px-2.5 py-1 text-neutral-500 dark:text-neutral-400 font-medium whitespace-nowrap border-r border-violet-100 dark:border-violet-800/50">
                        <Handle
                          type="target"
                          id={rowInputHandleId(si, ri)}
                          position={Position.Left}
                          className="!h-2.5 !w-2.5 !border-violet-400 !bg-white dark:!bg-violet-950"
                          style={{ left: -6, top: "50%", transform: "translateY(-50%)" }}
                        />
                        {row.parameter}
                      </td>
                      <td className="px-2.5 py-1 text-neutral-800 dark:text-neutral-200 font-mono whitespace-nowrap text-right">
                        {row.value}
                      </td>
                      <td className="px-1.5 py-1 text-neutral-400 dark:text-neutral-500 text-[10px] whitespace-nowrap">
                        {row.unit}
                      </td>
                      <td className="relative px-1.5 py-1 text-right whitespace-nowrap">
                        {row.source?.filename && row.source?.page ? (
                          <button
                            onClick={() => {
                              const highlights: PDFHighlight[] = row.source!.bbox?.length === 4
                                ? [{ page: row.source!.page!, bbox: row.source!.bbox! }]
                                : [];
                              onOpenPDF?.(row.source!.filename!, row.source!.page!, highlights);
                            }}
                            onMouseEnter={() => onPreviewSource?.(row.source!.filename!, row.source!.page!)}
                            onMouseLeave={() => onPreviewSource?.(null, null)}
                            className="inline-flex items-center gap-0.5 rounded border border-violet-200 px-1 py-0.5 text-[9px] font-medium text-violet-500 hover:bg-violet-50 dark:border-violet-700 dark:text-violet-400 dark:hover:bg-violet-950/40"
                            title={`Page ${row.source.page}`}
                          >
                            <FileText size={8} className="shrink-0" />
                            <span>p.{row.source.page}</span>
                          </button>
                        ) : null}
                        <Handle
                          type="source"
                          id={rowOutputHandleId(si, ri)}
                          position={Position.Right}
                          className="!h-2.5 !w-2.5 !border-violet-400 !bg-violet-500"
                          style={{ right: -6, top: "50%", transform: "translateY(-50%)" }}
                        />
                      </td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        ) : props.length > 0 ? (
          /* Legacy property rows */
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
                  <td className="px-2.5 py-1 text-neutral-500 dark:text-neutral-400 font-semibold">
                    Ref
                  </td>
                </tr>
              )}
              {props.map((p, i) => {
                const refButton = p.ref_filename && p.ref_page ? (
                  <button
                    onClick={() => onOpenPDF?.(p.ref_filename!, p.ref_page!, propertyHighlights(p))}
                    onMouseEnter={() => onPreviewSource?.(p.ref_filename!, p.ref_page!)}
                    onMouseLeave={() => onPreviewSource?.(null, null)}
                    className="inline-flex items-center gap-1 rounded-md border border-violet-200 px-1.5 py-0.5 text-[10px] font-medium text-violet-600 hover:bg-violet-50 dark:border-violet-700 dark:text-violet-300 dark:hover:bg-violet-950/40"
                    title={`Open source — page ${p.ref_page}`}
                  >
                    <FileText size={10} className="shrink-0" />
                    <span>ref</span>
                  </button>
                ) : null;
                const colSpan = isComparison ? 5 : 3;
                const prevGroup = i > 0 ? props[i - 1]?.group : undefined;
                const showGroup = p.group && p.group !== prevGroup;
                return (
                  <React.Fragment key={i}>
                    {showGroup && (
                      <tr className="bg-violet-100/70 dark:bg-violet-900/30">
                        <td colSpan={colSpan} className="px-2.5 py-1 text-[10px] font-bold text-violet-700 dark:text-violet-300 uppercase tracking-wide">
                          {p.group}
                        </td>
                      </tr>
                    )}
                    <tr className={i % 2 === 0 ? "bg-white dark:bg-neutral-900" : "bg-violet-50/50 dark:bg-violet-950/20"}>
                      <td className="relative px-2.5 py-1 text-neutral-500 dark:text-neutral-400 font-medium whitespace-nowrap border-r border-violet-100 dark:border-violet-800/50">
                        {p.ref_filename && p.ref_page ? (
                          <Handle
                            type="target"
                            id={propertyInputHandleId(i)}
                            position={Position.Left}
                            className="!h-2.5 !w-2.5 !border-violet-700 !bg-white dark:!bg-violet-950"
                            style={{ left: -8, top: "50%", transform: "translateY(-50%)" }}
                          />
                        ) : null}
                        {p.key}
                      </td>
                      {isComparison ? (
                        <>
                          <td className="px-2.5 py-1 text-neutral-800 dark:text-neutral-200 font-mono whitespace-nowrap border-r border-violet-100 dark:border-violet-800/50">
                            {p.left_value || "—"}
                          </td>
                          <td className="px-2.5 py-1 text-neutral-800 dark:text-neutral-200 font-mono whitespace-nowrap border-r border-violet-100 dark:border-violet-800/50">
                            {p.right_value || "—"}
                          </td>
                          <td className="px-2.5 py-1">
                            <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${comparisonTone(p.comparison_status)}`}>
                              {p.comparison_status || "different"}
                            </span>
                          </td>
                          <td className="relative px-2.5 py-1 text-right">
                            {refButton}
                            <Handle
                              type="source"
                              id={propertyOutputHandleId(i)}
                              position={Position.Right}
                              className="!h-2.5 !w-2.5 !border-violet-700 !bg-violet-500"
                              style={{ right: -8, top: "50%", transform: "translateY(-50%)" }}
                            />
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-2.5 py-1 text-neutral-800 dark:text-neutral-200 font-mono whitespace-nowrap">
                            {p.value}{p.unit ? <span className="text-neutral-400 dark:text-neutral-500 ml-1.5 font-sans text-[10px]">{p.unit}</span> : null}
                          </td>
                          <td className="relative px-2.5 py-1 text-right">
                            {refButton}
                            <Handle
                              type="source"
                              id={propertyOutputHandleId(i)}
                              position={Position.Right}
                              className="!h-2.5 !w-2.5 !border-violet-700 !bg-violet-500"
                              style={{ right: -8, top: "50%", transform: "translateY(-50%)" }}
                            />
                          </td>
                        </>
                      )}
                    </tr>
                  </React.Fragment>
                );
              })}
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
    </div>
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
              <div key={v.name} className="relative flex items-center gap-2 py-0.5">
                <Handle
                  type="target"
                  id={`param-in-${v.name}`}
                  position={Position.Left}
                  className="!bg-teal-400 !w-2.5 !h-2.5 !border-teal-700"
                  style={{ left: -8, top: "50%", transform: "translateY(-50%)" }}
                />
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

// ─── Pipeline Detail Modal ────────────────────────────────────────────────
interface PipelineDetail {
  filename: string;
  slug: string;
  bronze: { path: string; size_kb: number } | null;
  silver: {
    has_index: boolean;
    has_docling: boolean;
    page_count?: number;
    outline_count?: number;
    table_count?: number;
    figure_count?: number;
    pages: {
      page: number;
      has_png: boolean;
      has_raw_md: boolean;
      has_md: boolean;
      md_preview?: string;
    }[];
  } | null;
  gold: {
    pages: {
      page: number;
      region_count: number;
      region_kinds: string[];
    }[];
  } | null;
  status?: { stage: string; current: number; total: number };
}

function SilverPageDetail({ filename, page }: { filename: string; page: number }) {
  const [tab, setTab] = useState<"png" | "md" | "raw">("png");
  const [mdContent, setMdContent] = useState<string | null>(null);
  const [mdLoading, setMdLoading] = useState(false);

  const pngUrl = `${API_URL}/api/documents/silver/${encodeURIComponent(filename)}/page/${page}?kind=png`;

  useEffect(() => {
    if (tab === "png") return;
    setMdLoading(true);
    fetch(`${API_URL}/api/documents/silver/${encodeURIComponent(filename)}/page/${page}?kind=${tab}`)
      .then((r) => r.ok ? r.text() : null)
      .then((t) => setMdContent(t))
      .catch(() => setMdContent(null))
      .finally(() => setMdLoading(false));
  }, [filename, page, tab]);

  return (
    <div className="mx-1 mb-2 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
      <div className="flex border-b border-neutral-100 dark:border-neutral-800 bg-neutral-50/60 dark:bg-neutral-800/40">
        {(["png", "md", "raw"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-1.5 text-[10px] font-medium transition-colors ${
              tab === t
                ? "text-indigo-600 dark:text-indigo-400 bg-white dark:bg-neutral-900 border-b-2 border-indigo-500"
                : "text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
            }`}
          >
            {t === "png" ? "Page Image" : t === "md" ? "Polished MD" : "Raw MD"}
          </button>
        ))}
      </div>
      <div className="max-h-[360px] overflow-auto">
        {tab === "png" ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={pngUrl} alt={`Page ${page}`} className="w-full h-auto bg-neutral-100 dark:bg-neutral-800" loading="lazy" />
        ) : mdLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={14} className="animate-spin text-neutral-400" />
          </div>
        ) : mdContent ? (
          <div className="p-3">
            <div className="prose prose-xs dark:prose-invert max-w-none text-[11px] leading-relaxed">
              <ReactMarkdown>{mdContent}</ReactMarkdown>
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-neutral-400 text-center py-6">Not available</div>
        )}
      </div>
    </div>
  );
}

interface GoldPageRegion {
  id: string;
  kind: string;
  title: string;
  description?: string;
  markdown?: string;
  entities?: string[];
  tags?: string[];
  bbox?: number[];
  crops?: { png?: string; svg?: string };
}

function GoldPageDetail({ filename, slug, page }: { filename: string; slug: string; page: number }) {
  const [regions, setRegions] = useState<GoldPageRegion[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/documents/gold/${encodeURIComponent(filename)}/page/${page}/regions`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d?.regions) setRegions(d.regions); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [filename, page]);

  if (loading) return <div className="flex justify-center py-4"><Loader2 size={14} className="animate-spin text-neutral-400" /></div>;
  if (!regions.length) return <div className="text-[11px] text-neutral-400 text-center py-3">No regions loaded</div>;

  const kindColors: Record<string, string> = {
    chart: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
    spec_block: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
    table: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
    diagram: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    figure: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    caption: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
    text: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
  };

  return (
    <div className="mx-1 mb-2 space-y-0.5">
      {regions.map((r) => {
        const isOpen = expandedId === r.id;
        const svgUrl = r.crops?.svg
          ? `${API_URL}/api/documents/region-asset/${encodeURIComponent(slug)}/${r.crops.svg}`
          : null;
        const pngUrl = r.crops?.png
          ? `${API_URL}/api/documents/region-asset/${encodeURIComponent(slug)}/${r.crops.png}`
          : null;

        return (
          <div key={r.id} className="rounded-lg border border-neutral-100 dark:border-neutral-800 overflow-hidden">
            <button
              onClick={() => setExpandedId(isOpen ? null : r.id)}
              className="w-full flex items-center gap-2 px-2.5 py-2 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
            >
              <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium shrink-0 ${kindColors[r.kind] || kindColors.text}`}>
                {r.kind}
              </span>
              <span className="text-[11px] text-neutral-700 dark:text-neutral-200 truncate font-medium flex-1">
                {r.title}
              </span>
              {isOpen ? <ChevronUp size={12} className="text-neutral-400 shrink-0" /> : <ChevronDown size={12} className="text-neutral-400 shrink-0" />}
            </button>
            {isOpen && (
              <div className="px-2.5 pb-2.5 space-y-2">
                {r.description && (
                  <p className="text-[11px] text-neutral-500 dark:text-neutral-400">{r.description}</p>
                )}
                {r.entities && r.entities.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {r.entities.map((e) => (
                      <span key={e} className="text-[9px] px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">{e}</span>
                    ))}
                  </div>
                )}
                {r.tags && r.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {r.tags.map((t) => (
                      <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">#{t}</span>
                    ))}
                  </div>
                )}
                {r.markdown && (
                  <div className="rounded border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 p-2 max-h-[200px] overflow-auto">
                    <div className="prose prose-xs dark:prose-invert max-w-none text-[11px] leading-relaxed">
                      <ReactMarkdown>{r.markdown}</ReactMarkdown>
                    </div>
                  </div>
                )}
                {(svgUrl || pngUrl) && (
                  <div className="rounded border border-neutral-200 dark:border-neutral-700 overflow-hidden bg-white dark:bg-neutral-800">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={svgUrl || pngUrl!} alt={r.title} className="w-full h-auto" loading="lazy" />
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PipelineDetailModal({
  filename,
  onClose,
}: {
  filename: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<PipelineDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedSilverPage, setExpandedSilverPage] = useState<number | null>(null);
  const [expandedGoldPage, setExpandedGoldPage] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      fetch(`${API_URL}/api/documents/pipeline-detail/${encodeURIComponent(filename)}`)
        .then((r) => r.ok ? r.json() : null)
        .then((d) => { if (active) setDetail(d); })
        .catch(() => {})
        .finally(() => { if (active) setLoading(false); });
    };
    load();
    const iv = setInterval(load, 3000);
    return () => { active = false; clearInterval(iv); };
  }, [filename]);

  const isActive = detail?.status && detail.status.stage !== "done" && detail.status.stage !== "error";

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative w-[640px] max-h-[85vh] overflow-y-auto rounded-2xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-neutral-100 dark:border-neutral-800 bg-white/95 dark:bg-neutral-900/95 backdrop-blur px-5 py-4">
          <Activity size={18} className="text-indigo-500" />
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-neutral-800 dark:text-neutral-100 truncate">
              Pipeline: {filename}
            </h2>
            {detail?.slug && (
              <div className="text-[10px] text-neutral-400 font-mono">{detail.slug}</div>
            )}
          </div>
          {isActive && (
            <span className="flex items-center gap-1.5 rounded-full bg-indigo-100 dark:bg-indigo-900/40 px-2.5 py-1 text-[10px] font-medium text-indigo-600 dark:text-indigo-400">
              <Loader2 size={10} className="animate-spin" />
              {detail!.status!.stage} {detail!.status!.current}/{detail!.status!.total}
            </span>
          )}
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors">
            <XCircle size={16} className="text-neutral-400" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={20} className="animate-spin text-neutral-400" />
          </div>
        ) : !detail ? (
          <div className="text-sm text-neutral-400 text-center py-12">Could not load pipeline details.</div>
        ) : (
          <div className="px-5 py-4 space-y-4">
            {/* Bronze */}
            <PipelineSection
              title="Bronze"
              subtitle="Raw PDF"
              icon={<FileText size={14} />}
              status={detail.bronze ? "done" : "missing"}
            >
              {detail.bronze ? (
                <div className="text-[11px] text-neutral-500 dark:text-neutral-400">
                  {detail.bronze.size_kb} KB
                </div>
              ) : (
                <div className="text-[11px] text-neutral-400 italic">No PDF in bronze directory</div>
              )}
            </PipelineSection>

            {/* Silver */}
            <PipelineSection
              title="Silver"
              subtitle="Docling extraction"
              icon={<Layers size={14} />}
              status={detail.silver ? (detail.silver.has_index ? "done" : "partial") : "missing"}
            >
              {detail.silver ? (
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2 text-[11px]">
                    <Pill ok={detail.silver.has_docling}>docling.json</Pill>
                    <Pill ok={detail.silver.has_index}>index.json</Pill>
                    {detail.silver.page_count != null && (
                      <span className="text-neutral-500">{detail.silver.page_count} pages</span>
                    )}
                    {(detail.silver.outline_count ?? 0) > 0 && (
                      <span className="text-neutral-500">{detail.silver.outline_count} headings</span>
                    )}
                    {(detail.silver.table_count ?? 0) > 0 && (
                      <span className="text-neutral-500">{detail.silver.table_count} tables</span>
                    )}
                    {(detail.silver.figure_count ?? 0) > 0 && (
                      <span className="text-neutral-500">{detail.silver.figure_count} figures</span>
                    )}
                  </div>
                  {detail.silver.pages.length > 0 && (
                    <div className="space-y-0.5">
                      {detail.silver.pages.map((p) => (
                        <div key={p.page}>
                          <button
                            onClick={() => setExpandedSilverPage(expandedSilverPage === p.page ? null : p.page)}
                            className="w-full flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors text-left"
                          >
                            <span className="text-[10px] font-mono text-neutral-500 w-5 text-right shrink-0">
                              {p.page}
                            </span>
                            <Pill ok={p.has_png} small>png</Pill>
                            <Pill ok={p.has_raw_md} small>raw</Pill>
                            <Pill ok={p.has_md} small>md</Pill>
                            {expandedSilverPage === p.page
                              ? <ChevronUp size={10} className="ml-auto text-neutral-400" />
                              : <ChevronDown size={10} className="ml-auto text-neutral-400" />}
                          </button>
                          {expandedSilverPage === p.page && (
                            <SilverPageDetail filename={filename} page={p.page} />
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-[11px] text-neutral-400 italic">Not yet processed</div>
              )}
            </PipelineSection>

            {/* Gold */}
            <PipelineSection
              title="Gold"
              subtitle="LLM polish + regions"
              icon={<Cpu size={14} />}
              status={detail.gold && detail.gold.pages.length > 0 ? "done" : isActive ? "running" : "missing"}
            >
              {detail.gold && detail.gold.pages.length > 0 ? (
                <div className="space-y-0.5">
                  {detail.gold.pages.map((p) => (
                    <div key={p.page}>
                      <button
                        onClick={() => setExpandedGoldPage(expandedGoldPage === p.page ? null : p.page)}
                        className="w-full flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors text-left"
                      >
                        <span className="font-mono text-neutral-500 text-[10px] w-5 text-right shrink-0">{p.page}</span>
                        <span className="text-[11px] text-neutral-600 dark:text-neutral-300">{p.region_count} regions</span>
                        <div className="flex flex-wrap gap-1 flex-1 min-w-0">
                          {p.region_kinds.map((k, i) => (
                            <span key={i} className="px-1.5 py-0.5 rounded text-[9px] bg-neutral-100 dark:bg-neutral-800 text-neutral-500">{k}</span>
                          ))}
                        </div>
                        {expandedGoldPage === p.page
                          ? <ChevronUp size={10} className="text-neutral-400 shrink-0" />
                          : <ChevronDown size={10} className="text-neutral-400 shrink-0" />}
                      </button>
                      {expandedGoldPage === p.page && (
                        <GoldPageDetail filename={filename} slug={detail?.slug || ""} page={p.page} />
                      )}
                    </div>
                  ))}
                </div>
              ) : isActive ? (
                <div className="flex items-center gap-2 text-[11px] text-indigo-500">
                  <Loader2 size={12} className="animate-spin" />
                  Running...
                </div>
              ) : (
                <div className="text-[11px] text-neutral-400 italic">Not yet extracted</div>
              )}
            </PipelineSection>
          </div>
        )}
      </div>
    </div>
  );
}

function PipelineSection({
  title,
  subtitle,
  icon,
  status,
  children,
}: {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  status: "done" | "partial" | "running" | "missing";
  children: React.ReactNode;
}) {
  const statusColors = {
    done: "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400",
    partial: "bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400",
    running: "bg-indigo-100 text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-400",
    missing: "bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500",
  };
  const statusLabels = { done: "done", partial: "partial", running: "running", missing: "—" };

  return (
    <div className="rounded-xl border border-neutral-100 dark:border-neutral-800 overflow-hidden">
      <div className="flex items-center gap-2.5 px-3 py-2.5 bg-neutral-50/60 dark:bg-neutral-800/40">
        <span className="text-indigo-500">{icon}</span>
        <div className="flex-1 min-w-0">
          <span className="text-xs font-semibold text-neutral-700 dark:text-neutral-200">{title}</span>
          <span className="ml-1.5 text-[10px] text-neutral-400">{subtitle}</span>
        </div>
        <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full ${statusColors[status]}`}>
          {statusLabels[status]}
        </span>
      </div>
      <div className="px-3 py-2">{children}</div>
    </div>
  );
}

function Pill({ ok, small, children }: { ok: boolean; small?: boolean; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-0.5 rounded-full font-medium ${
      small ? "text-[9px] px-1 py-0" : "text-[10px] px-1.5 py-0.5"
    } ${ok
      ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400"
      : "bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500"
    }`}>
      {ok ? <CheckCircle2 size={small ? 8 : 10} /> : <CircleDashed size={small ? 8 : 10} />}
      {children}
    </span>
  );
}

// ─── Document Region Map ──────────────────────────────────────────────────

interface GoldMapRegion {
  id: string;
  kind: string;
  title: string;
  description?: string;
  bbox?: number[];  // [left, top, right, bottom] BOTTOMLEFT origin
  entities?: string[];
  crops?: { png?: string; svg?: string };
}

interface GoldMapData {
  slug: string;
  page_count: number;
  page_width: number;
  page_height: number;
  pages: Record<string, GoldMapRegion[]>;
}

function DocumentRegionMap({
  filename,
  onDragRegion,
}: {
  filename: string;
  onDragRegion?: (region: GoldMapRegion, page: number) => void;
}) {
  const [mapData, setMapData] = useState<GoldMapData | null>(null);
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(152);

  useEffect(() => {
    fetch(`${API_URL}/api/documents/gold-map/${encodeURIComponent(filename)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d?.pages && Object.keys(d.pages).length > 0) setMapData(d); })
      .catch(() => {});
  }, [filename]);

  // Measure container width (must be before early return to keep hooks order stable)
  useEffect(() => {
    if (!mapData) return;
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setContainerWidth(e.contentRect.width);
    });
    ro.observe(el);
    setContainerWidth(el.clientWidth || 152);
    return () => ro.disconnect();
  }, [mapData]);

  if (!mapData) return null;

  const { slug, page_width, page_height, page_count } = mapData;
  const scale = containerWidth / page_width;
  const renderHeight = page_height * scale;

  const pageNums = Array.from({ length: page_count }, (_, i) => i + 1);
  const regions = mapData.pages[String(currentPage)] || [];

  const kindColors: Record<string, string> = {
    chart: "rgba(147, 51, 234, 0.18)",
    spec_block: "rgba(59, 130, 246, 0.18)",
    table: "rgba(59, 130, 246, 0.18)",
    diagram: "rgba(245, 158, 11, 0.18)",
    figure: "rgba(245, 158, 11, 0.18)",
    text: "rgba(107, 114, 128, 0.12)",
    caption: "rgba(20, 184, 166, 0.15)",
  };
  const kindBorders: Record<string, string> = {
    chart: "rgba(147, 51, 234, 0.5)",
    spec_block: "rgba(59, 130, 246, 0.5)",
    table: "rgba(59, 130, 246, 0.5)",
    diagram: "rgba(245, 158, 11, 0.5)",
    figure: "rgba(245, 158, 11, 0.5)",
    text: "rgba(107, 114, 128, 0.3)",
    caption: "rgba(20, 184, 166, 0.4)",
  };

  return (
    <div ref={containerRef} className="relative w-full" style={{ height: renderHeight }}>
      {/* Page PNG background */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`${API_URL}/api/documents/silver/${encodeURIComponent(filename)}/page/${currentPage}?kind=png`}
        alt={`Page ${currentPage}`}
        className="absolute inset-0 w-full h-full object-cover"
        loading="lazy"
      />
      {/* Region overlays */}
      {regions.map((r) => {
        if (!r.bbox || r.bbox.length < 4) return null;
        const [left = 0, top = 0, right = 0, bottom = 0] = r.bbox;
        // Convert BOTTOMLEFT to top-left CSS coordinates
        const cssLeft = left * scale;
        const cssTop = (page_height - top) * scale;
        const cssWidth = (right - left) * scale;
        const cssHeight = (top - bottom) * scale;
        const isHovered = hoveredRegion === r.id;

        return (
          <div
            key={r.id}
            className="absolute cursor-grab transition-all duration-150 nodrag nopan"
            style={{
              left: cssLeft,
              top: cssTop,
              width: cssWidth,
              height: cssHeight,
              background: isHovered ? (kindColors[r.kind] || kindColors.text)?.replace(/[\d.]+\)$/, "0.35)") : (kindColors[r.kind] || kindColors.text),
              border: `1px solid ${isHovered ? (kindBorders[r.kind] || kindBorders.text)?.replace(/[\d.]+\)$/, "0.8)") : (kindBorders[r.kind] || kindBorders.text)}`,
              borderRadius: 2,
              zIndex: isHovered ? 10 : 1,
              transform: isHovered ? "scale(1.01)" : undefined,
            }}
            title={`${r.kind}: ${r.title}`}
            onMouseEnter={() => setHoveredRegion(r.id)}
            onMouseLeave={() => setHoveredRegion(null)}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData("application/anchor-region", JSON.stringify({
                ...r,
                page: currentPage,
                filename,
                slug,
              }));
              e.dataTransfer.effectAllowed = "copy";
              onDragRegion?.(r, currentPage);
            }}
          >
            {/* Show title on hover */}
            {isHovered && cssWidth > 20 && (
              <div
                className="absolute left-0 right-0 pointer-events-none overflow-hidden"
                style={{ top: -14 }}
              >
                <span className="text-[7px] font-medium text-neutral-700 dark:text-neutral-200 bg-white/90 dark:bg-neutral-900/90 px-1 py-0.5 rounded shadow-sm whitespace-nowrap">
                  {r.title}
                </span>
              </div>
            )}
          </div>
        );
      })}
      {/* Page navigation */}
      {page_count > 1 && (
        <div className="absolute bottom-1 left-1/2 -translate-x-1/2 flex items-center gap-0.5 bg-black/50 rounded-full px-1.5 py-0.5 z-20 nodrag nopan">
          {pageNums.map((pg) => (
            <button
              key={pg}
              onClick={(e) => { e.stopPropagation(); setCurrentPage(pg); }}
              className={`w-4 h-4 flex items-center justify-center rounded-full text-[8px] font-medium transition-colors ${
                currentPage === pg
                  ? "bg-white text-neutral-800"
                  : "text-white/70 hover:text-white hover:bg-white/20"
              }`}
            >
              {pg}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Contents Sidecart ────────────────────────────────────────────────────
// Drill-down panel that opens to the right of the document node.
// Levels: root → page → region detail
// Items are draggable to the canvas.

type SidecartLevel = { kind: "root" } | { kind: "page"; page: number } | { kind: "region"; page: number; regionId: string };

interface DocIndex {
  document?: { filename?: string; title?: string; page_count?: number };
  outline?: { level: number; title: string; page: number }[];
  tables?: { id: string; page: number; caption: string; shape?: { rows: number; cols: number }; header_row?: string[]; first_column_values?: string[] }[];
  figures?: { page: number; caption: string }[];
}

function ContentsSidecart({
  filename,
  anchorRef,
  onClose,
  onOpenPDF,
}: {
  filename: string;
  anchorRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onOpenPDF: (filename: string, page: number, highlights: PDFHighlight[]) => void;
}) {
  const [level, setLevel] = useState<SidecartLevel>({ kind: "root" });
  const [docIndex, setDocIndex] = useState<DocIndex | null>(null);
  const [goldRegions, setGoldRegions] = useState<Record<number, GoldRegion[]>>({});
  const [loading, setLoading] = useState(true);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const slug = filename.replace(/\.pdf$/i, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase();

  // Position relative to anchor node
  useEffect(() => {
    const el = anchorRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setPos({ top: rect.top, left: rect.right + 12 });
  }, [anchorRef]);

  // Fetch index + gold regions
  useEffect(() => {
    const fn = encodeURIComponent(filename);
    Promise.all([
      fetch(`${API_URL}/api/documents/index/${fn}`).then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch(`${API_URL}/api/documents/regions/${fn}`).then((r) => r.ok ? r.json() : null).catch(() => null),
    ]).then(([idx, reg]) => {
      if (idx) setDocIndex(idx);
      if (reg?.pages) {
        const byPage: Record<number, GoldRegion[]> = {};
        for (const [p, rs] of Object.entries(reg.pages)) {
          byPage[Number(p)] = rs as GoldRegion[];
        }
        setGoldRegions(byPage);
      }
    }).finally(() => setLoading(false));
  }, [filename]);

  const pageCount = docIndex?.document?.page_count || Math.max(...Object.keys(goldRegions).map(Number), 0);
  const pages = Array.from({ length: pageCount }, (_, i) => i + 1);

  // Count items per page
  const pageItemCount = (pg: number) => {
    let count = goldRegions[pg]?.length || 0;
    if (docIndex?.outline) count += docIndex.outline.filter((o) => o.page === pg).length;
    if (docIndex?.tables) count += docIndex.tables.filter((t) => t.page === pg).length;
    if (docIndex?.figures) count += docIndex.figures.filter((f) => f.page === pg).length;
    return count;
  };

  const makeDragData = (region: GoldRegion) => JSON.stringify({
    ...region,
    filename,
    slug,
  });

  const kindBadge = (kind: string) => {
    const map: Record<string, string> = {
      chart: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
      spec_block: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
      table: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
      diagram: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
      figure: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
      text: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
      caption: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
    };
    return map[kind] || map.text;
  };

  const renderRoot = () => (
    <div className="flex flex-col">
      {pages.map((pg) => {
        const count = pageItemCount(pg);
        const regions = goldRegions[pg] || [];
        const hasGold = regions.length > 0;
        return (
          <button
            key={pg}
            onClick={() => setLevel({ kind: "page", page: pg })}
            className="flex items-center gap-3 px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors border-b border-neutral-100 dark:border-neutral-800 text-left"
          >
            {/* Page thumbnail */}
            <div className="w-10 h-14 rounded border border-neutral-200 dark:border-neutral-700 overflow-hidden bg-neutral-100 dark:bg-neutral-800 shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${API_URL}/api/documents/silver/${encodeURIComponent(filename)}/page/${pg}?kind=png`}
                alt={`Page ${pg}`}
                className="w-full h-full object-cover object-top"
                loading="lazy"
              />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-neutral-800 dark:text-neutral-200">
                Page {pg}
              </div>
              <div className="text-[10px] text-neutral-500 dark:text-neutral-400 mt-0.5">
                {count} item{count !== 1 ? "s" : ""}
                {hasGold && <span className="ml-1 text-emerald-600 dark:text-emerald-400">· {regions.length} regions</span>}
              </div>
              {/* Show first few region titles */}
              {regions.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {regions.slice(0, 3).map((r) => (
                    <span key={r.id} className={`text-[8px] px-1.5 py-0.5 rounded-full ${kindBadge(r.kind)}`}>
                      {r.title}
                    </span>
                  ))}
                  {regions.length > 3 && <span className="text-[8px] text-neutral-400">+{regions.length - 3}</span>}
                </div>
              )}
            </div>
            <ChevronRight size={14} className="text-neutral-400 shrink-0" />
          </button>
        );
      })}
    </div>
  );

  const renderPage = (pg: number) => {
    const regions = goldRegions[pg] || [];
    const outline = docIndex?.outline?.filter((o) => o.page === pg) || [];
    const tables = docIndex?.tables?.filter((t) => t.page === pg) || [];
    const figures = docIndex?.figures?.filter((f) => f.page === pg) || [];

    return (
      <div className="flex flex-col">
        {/* Page preview */}
        <div
          className="mx-4 mt-3 mb-2 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden cursor-pointer hover:ring-2 hover:ring-indigo-300 transition-all"
          onClick={() => onOpenPDF(filename, pg, [])}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`${API_URL}/api/documents/silver/${encodeURIComponent(filename)}/page/${pg}?kind=png`}
            alt={`Page ${pg}`}
            className="w-full h-auto"
            loading="lazy"
          />
        </div>

        {/* Outline entries */}
        {outline.length > 0 && (
          <div className="px-4 py-2 border-b border-neutral-100 dark:border-neutral-800">
            <div className="text-[10px] font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">Sections</div>
            {outline.map((o, i) => (
              <button
                key={i}
                onClick={() => onOpenPDF(filename, pg, [])}
                className="w-full text-left px-2 py-1 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 rounded transition-colors"
                style={{ paddingLeft: `${8 + (o.level - 1) * 12}px` }}
              >
                <span className="text-xs text-neutral-700 dark:text-neutral-300">{o.title}</span>
              </button>
            ))}
          </div>
        )}

        {/* Tables from index */}
        {tables.length > 0 && (
          <div className="px-4 py-2 border-b border-neutral-100 dark:border-neutral-800">
            <div className="text-[10px] font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">Tables</div>
            {tables.map((t) => (
              <button
                key={t.id}
                onClick={() => onOpenPDF(filename, pg, [])}
                className="w-full text-left px-2 py-1.5 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 rounded transition-colors"
              >
                <div className="flex items-center gap-1.5">
                  <Table2 size={11} className="text-blue-500 shrink-0" />
                  <span className="text-xs text-neutral-700 dark:text-neutral-300">{t.caption || "Untitled"}</span>
                </div>
                {t.first_column_values && t.first_column_values.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1 pl-5">
                    {t.first_column_values.slice(0, 6).map((v) => (
                      <span key={v} className="text-[9px] px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">{v}</span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        )}

        {/* Figures from index */}
        {figures.length > 0 && (
          <div className="px-4 py-2 border-b border-neutral-100 dark:border-neutral-800">
            <div className="text-[10px] font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">Figures</div>
            {figures.map((f, i) => (
              <button
                key={i}
                onClick={() => onOpenPDF(filename, pg, [])}
                className="w-full text-left px-2 py-1 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 rounded transition-colors"
              >
                <div className="flex items-center gap-1.5">
                  <Image size={11} className="text-amber-500 shrink-0" />
                  <span className="text-xs text-neutral-700 dark:text-neutral-300">{f.caption || "Untitled"}</span>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Gold regions — draggable */}
        {regions.length > 0 && (
          <div className="px-4 py-2">
            <div className="text-[10px] font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">Regions</div>
            <div className="flex flex-col gap-2">
              {regions.map((r) => {
                const svgUrl = r.crops?.svg
                  ? `${API_URL}/api/documents/region-asset/${encodeURIComponent(slug)}/${r.crops.svg}`
                  : null;
                const pngUrl = r.crops?.png
                  ? `${API_URL}/api/documents/region-asset/${encodeURIComponent(slug)}/${r.crops.png}`
                  : null;
                const previewUrl = svgUrl || pngUrl;

                return (
                  <div
                    key={r.id}
                    className="group rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-850 overflow-hidden hover:border-indigo-300 dark:hover:border-indigo-600 hover:shadow-md transition-all cursor-grab active:cursor-grabbing"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("application/anchor-region", makeDragData(r));
                      e.dataTransfer.effectAllowed = "copy";
                    }}
                  >
                    {/* Region header */}
                    <div className="flex items-center gap-2 px-3 py-2">
                      <GripVertical size={12} className="text-neutral-300 dark:text-neutral-600 shrink-0 group-hover:text-indigo-400 transition-colors" />
                      <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium shrink-0 ${kindBadge(r.kind)}`}>
                        {r.kind}
                      </span>
                      <span className="text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate">
                        {r.title}
                      </span>
                    </div>
                    {/* SVG/PNG preview */}
                    {previewUrl && (
                      <div className="px-2 pb-2">
                        <div className="rounded border border-neutral-100 dark:border-neutral-700 overflow-hidden bg-neutral-50 dark:bg-neutral-800">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={previewUrl} alt={r.title} className="w-full h-auto" loading="lazy" />
                        </div>
                      </div>
                    )}
                    {/* Description */}
                    {r.description && (
                      <div className="px-3 pb-2 text-[10px] text-neutral-500 dark:text-neutral-400 leading-snug">
                        {r.description}
                      </div>
                    )}
                    {/* Entities */}
                    {r.entities.length > 0 && (
                      <div className="flex flex-wrap gap-1 px-3 pb-2">
                        {r.entities.map((e) => (
                          <span key={e} className="text-[8px] px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">{e}</span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {outline.length === 0 && tables.length === 0 && figures.length === 0 && regions.length === 0 && (
          <div className="px-4 py-6 text-center text-xs text-neutral-400">No content extracted for this page</div>
        )}
      </div>
    );
  };

  const title = level.kind === "root"
    ? "Contents"
    : level.kind === "page"
    ? `Page ${level.page}`
    : "Region";

  return createPortal(
    <div
      className="fixed z-[9999] flex flex-col bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-2xl shadow-2xl overflow-hidden"
      style={{
        top: pos.top,
        left: pos.left,
        width: 340,
        maxHeight: "min(600px, calc(100vh - 80px))",
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-neutral-100 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-850 shrink-0">
        {level.kind !== "root" && (
          <button
            onClick={() => setLevel(level.kind === "region" ? { kind: "page", page: level.page } : { kind: "root" })}
            className="p-1 -ml-1 rounded-lg hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
          >
            <ChevronLeft size={16} className="text-neutral-500" />
          </button>
        )}
        <Layers size={14} className="text-neutral-500 shrink-0" />
        <span className="text-sm font-semibold text-neutral-800 dark:text-neutral-200 flex-1">{title}</span>
        <button
          onClick={onClose}
          className="p-1 -mr-1 rounded-lg hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
        >
          <X size={14} className="text-neutral-400" />
        </button>
      </div>
      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={18} className="animate-spin text-neutral-400" />
          </div>
        ) : level.kind === "root" ? (
          renderRoot()
        ) : level.kind === "page" ? (
          renderPage(level.page)
        ) : null}
      </div>
    </div>,
    document.body,
  );
}

// ─── Document Node ─────────────────────────────────────────────────────────
interface GoldRegion {
  id: string;
  page: number;
  kind: string;
  title: string;
  description: string;
  entities: string[];
  crops?: { png?: string; svg?: string };
}

export interface DocumentNodeData extends Record<string, unknown> {
  item?: CanvasNodeData;
  doc?: KBDocument;
  isActive: boolean;
  previewPage?: number | null;
  onActivate: (id: string) => void;
  onOpenPDF: (filename: string, page: number, highlights: PDFHighlight[]) => void;
  onRemoveFromCanvas?: (docId: string) => void;
  evidenceCount: number;
}

export function DocumentNode({ data }: NodeProps) {
  const { item, doc, isActive, previewPage, onActivate, onOpenPDF, onRemoveFromCanvas, evidenceCount } = data as DocumentNodeData;
  const resolvedDoc = doc ?? item?.metadata?.document;
  if (!resolvedDoc) return null;
  const docData = resolvedDoc;
  const isProcessing = docData.status === "processing" || docData.status === "pending";
  const isError = docData.status === "error" || docData.status === "failed";
  const stem = docData.filename.replace(/\.[^.]+$/, "");
  const coverUrl = buildPageImageUrl(docData.filename, 1);
  const hoveredCoverUrl = previewPage && previewPage > 1 ? buildPageImageUrl(docData.filename, previewPage) : null;
  const isPreviewing = !!hoveredCoverUrl;

  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<{ stage: string; current: number; total: number } | null>(null);
  const [pipelineModalOpen, setPipelineModalOpen] = useState(false);
  const [contentsOpen, setContentsOpen] = useState(false);
  const nodeRef = useRef<HTMLDivElement>(null);
  const [hasGoldMap, setHasGoldMap] = useState(false);

  // Poll pipeline progress while active
  useEffect(() => {
    if (!docData.filename) return;
    let active = true;
    const poll = () => {
      fetch(`${API_URL}/api/documents/pipeline-status?filenames=${encodeURIComponent(docData.filename)}`)
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
          if (!active) return;
          const status = data?.[docData.filename];
          setPipelineStatus(status ?? null);
          if (status && status.stage !== "done" && status.stage !== "error") {
            timer = setTimeout(poll, 2000);
          } else if (status?.stage === "done") {
            // Pipeline finished — check for gold map
            fetch(`${API_URL}/api/documents/gold-map/${encodeURIComponent(docData.filename)}`)
              .then((r) => r.ok ? r.json() : null)
              .then((d) => { if (active && d?.pages && Object.keys(d.pages).length > 0) setHasGoldMap(true); })
              .catch(() => {});
          }
        })
        .catch(() => {});
    };
    let timer = setTimeout(poll, 1000);
    return () => { active = false; clearTimeout(timer); };
  }, [docData.filename]);

  // Check for gold map on mount
  useEffect(() => {
    if (!docData.filename) return;
    let active = true;
    fetch(`${API_URL}/api/documents/gold-map/${encodeURIComponent(docData.filename)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (active && d?.pages && Object.keys(d.pages).length > 0) setHasGoldMap(true); })
      .catch(() => {});
    return () => { active = false; };
  }, [docData.filename]);

  useEffect(() => {
    if (!ctxMenu) return;
    const close = () => setCtxMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("contextmenu", close);
    return () => { window.removeEventListener("click", close); window.removeEventListener("contextmenu", close); };
  }, [ctxMenu]);

  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2.5 !w-2.5 !bg-indigo-400 !border-indigo-600"
      />
      <Handle
        type="source"
        id="doc-evidence-out"
        position={Position.Right}
        className={`!h-2.5 !w-2.5 !border-indigo-700 ${isPreviewing ? "!bg-indigo-500" : "!bg-indigo-400 dark:!bg-indigo-500"}`}
        style={{ right: -8, top: "50%", transform: "translateY(-50%)" }}
      />
      <Handle
        type="source"
        id="doc-out-bottom"
        position={Position.Bottom}
        className="!h-2.5 !w-2.5 !bg-indigo-400 !border-indigo-600"
      />
      <div
        ref={nodeRef}
        onContextMenu={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setCtxMenu({ x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY });
        }}
        title={docData.filename}
        className={`group relative flex flex-col overflow-hidden rounded-[20px] border transition-all shadow-[0_14px_30px_rgba(15,23,42,0.16)] text-left w-full ${
          isActive
            ? "border-indigo-400 dark:border-indigo-500 bg-indigo-50 dark:bg-indigo-950/50"
            : "border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 hover:border-indigo-300 dark:hover:border-indigo-600"
        }`}
        style={{
          width: 176,
          boxShadow: isPreviewing
            ? "0 18px 42px rgba(99, 102, 241, 0.24), 0 0 0 2px rgba(99, 102, 241, 0.16)"
            : undefined,
          transform: isPreviewing ? "translateY(-2px)" : undefined,
        }}
      >
        <div className="relative px-3 pt-3">
          <div className={`relative overflow-hidden rounded-[14px] border shadow-sm ${
            isActive
              ? "border-indigo-200 dark:border-indigo-700"
              : "border-neutral-200 dark:border-neutral-700"
          }`} style={{ aspectRatio: "0.707 / 1" }}>
            <div className={`absolute inset-0 z-10 transition-all duration-200 pointer-events-none ${
              isPreviewing
                ? "bg-gradient-to-b from-indigo-400/10 via-transparent to-indigo-950/16"
                : hasGoldMap ? "" : "bg-gradient-to-b from-transparent via-transparent to-neutral-950/10"
            }`} />
            {hasGoldMap ? (
              <div className="absolute inset-0 nodrag nopan">
                <DocumentRegionMap filename={docData.filename} />
              </div>
            ) : (
              <div
                className="absolute inset-0 cursor-pointer"
                onClick={() => {
                  onActivate(isActive ? "" : docData.document_id);
                  onOpenPDF(docData.filename, 1, []);
                }}
              >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={coverUrl}
                alt={`${docData.filename} cover`}
                className={`absolute inset-0 block h-full w-full object-cover object-top bg-neutral-100 dark:bg-neutral-800 transition-all duration-300 ${
                  isPreviewing ? "scale-[0.985] opacity-0" : "scale-100 opacity-100"
                }`}
                loading="lazy"
              />
              {hoveredCoverUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={hoveredCoverUrl}
                alt={`${docData.filename} preview page ${previewPage}`}
                className={`absolute inset-0 block h-full w-full object-cover object-top bg-neutral-100 dark:bg-neutral-800 transition-all duration-300 ${
                  isPreviewing ? "scale-100 opacity-100" : "scale-[1.015] opacity-0"
                }`}
                loading="lazy"
              />
            ) : null}
              </div>
            )}
            <div className="pointer-events-none absolute right-2 top-2 z-20 flex items-center gap-1">
              {isPreviewing ? (
                <>
                  <span className="rounded-full bg-indigo-600/92 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-white shadow-sm">
                    preview
                  </span>
                  <span className="rounded-full bg-indigo-500/92 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-white shadow-sm">
                    p.{previewPage}
                  </span>
                </>
              ) : null}
              <span className="rounded-full bg-white/92 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-neutral-700 shadow-sm dark:bg-neutral-900/92 dark:text-neutral-200">
                PDF
              </span>
              {isProcessing ? (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/92 shadow-sm dark:bg-neutral-900/92">
                  <Loader2 size={11} className="animate-spin text-amber-500" />
                </span>
              ) : isError ? (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/92 shadow-sm dark:bg-neutral-900/92">
                  <XCircle size={11} className="text-red-500" />
                </span>
              ) : (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/92 shadow-sm dark:bg-neutral-900/92">
                  <FileText size={11} className={isActive ? "text-indigo-600 dark:text-indigo-400" : "text-neutral-500 dark:text-neutral-300"} />
                </span>
              )}
            </div>
          </div>
          {/* Pipeline progress bar */}
          {pipelineStatus && pipelineStatus.stage !== "done" && pipelineStatus.stage !== "error" && (
            <div className="absolute bottom-0 left-0 right-0 z-20">
              <div className="h-[3px] w-full bg-neutral-200/60 dark:bg-neutral-700/60">
                <div
                  className="h-full bg-indigo-500 transition-all duration-500 ease-out"
                  style={{ width: `${pipelineStatus.total > 0 ? (pipelineStatus.current / pipelineStatus.total) * 100 : 0}%` }}
                />
              </div>
            </div>
          )}
        </div>
        <div
          className="flex flex-col gap-2 px-3 pb-3 pt-2 cursor-pointer"
          onClick={() => {
            onActivate(isActive ? "" : docData.document_id);
            onOpenPDF(docData.filename, 1, []);
          }}
        >
          <div className="min-w-0">
            <div className={`text-[11px] font-semibold leading-tight truncate ${
              isActive ? "text-indigo-700 dark:text-indigo-300" : "text-neutral-800 dark:text-neutral-200"
            }`}>
              {stem}
            </div>
            {pipelineStatus && pipelineStatus.stage !== "done" ? (
              <div className="mt-0.5 text-[10px] text-indigo-500 dark:text-indigo-400">
                {pipelineStatus.stage === "error" ? "pipeline error" :
                 pipelineStatus.stage === "starting" ? "starting pipeline..." :
                 `${pipelineStatus.stage} ${pipelineStatus.current}/${pipelineStatus.total}`}
              </div>
            ) : (
              <div className="mt-0.5 text-[10px] uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-500">
                Product leaflet
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); setPipelineModalOpen(true); }}
              onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); setPipelineModalOpen(true); } }}
              className={`text-[10px] px-1.5 py-0.5 rounded-full cursor-pointer hover:ring-1 hover:ring-current/20 transition-all ${
                isProcessing
                  ? "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400"
                  : isError
                  ? "bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400"
                  : "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400"
              }`}
            >
              {isProcessing ? "processing" : isError ? "error" : `${docData.node_count} pages`}
            </span>
            {evidenceCount > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-100 dark:bg-teal-900/40 text-teal-700 dark:text-teal-300">
                {evidenceCount} ref{evidenceCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Contents button */}
      <button
        onClick={(e) => { e.stopPropagation(); setContentsOpen(!contentsOpen); }}
        className="w-full flex items-center justify-center gap-1 py-1 text-[10px] text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
      >
        <Layers size={10} />
        <span>{contentsOpen ? "hide" : "contents"}</span>
        {contentsOpen ? <ChevronUp size={10} /> : <ChevronRight size={10} />}
      </button>

      {/* Sidecart */}
      {contentsOpen && (
        <ContentsSidecart
          filename={docData.filename}
          anchorRef={nodeRef}
          onClose={() => setContentsOpen(false)}
          onOpenPDF={onOpenPDF}
        />
      )}
      {ctxMenu && (
        <div
          className="absolute z-50 min-w-[140px] rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow-lg py-1"
          style={{ left: ctxMenu.x, top: ctxMenu.y }}
        >
          <button
            onClick={(e) => { e.stopPropagation(); setCtxMenu(null); setPipelineModalOpen(true); }}
            className="w-full text-left px-3 py-1.5 text-xs text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 flex items-center gap-2"
          >
            <Activity size={12} />
            Pipeline details
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setCtxMenu(null); onRemoveFromCanvas?.(docData.document_id); }}
            className="w-full text-left px-3 py-1.5 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 flex items-center gap-2"
          >
            <XCircle size={12} />
            Remove from canvas
          </button>
        </div>
      )}
      {pipelineModalOpen && createPortal(
        <PipelineDetailModal
          filename={docData.filename}
          onClose={() => setPipelineModalOpen(false)}
        />,
        document.body,
      )}
    </>
  );
}

// ─── Funnel Node ──────────────────────────────────────────────────────────
export interface FunnelNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  connectedDocCount: number;
}

export function FunnelNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, connectedDocCount } = data as FunnelNodeData;
  const label = node.funnel_label || "Funnel";

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-teal-500 !border-teal-700" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-teal-500 !border-teal-700" />
      <Handle type="target" position={Position.Right} id="right" className="!bg-teal-500 !border-teal-700" />
      <div
        className="relative select-none"
        style={{ width: '100%', height: '100%' }}
      >
        <div className="absolute inset-0 border-[3px] border-teal-500 bg-white shadow-md dark:border-teal-500 dark:bg-neutral-900"
          style={{ clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" }}
        />
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 px-6 text-center">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-100 dark:bg-teal-900">
            <Filter size={16} className="text-teal-600 dark:text-teal-400" />
          </div>
          <span className="text-[11px] font-semibold text-teal-700 dark:text-teal-300 break-words">
            {label}
          </span>
          {connectedDocCount > 0 && (
            <span className="rounded-full bg-teal-100 px-1.5 py-0.5 text-[10px] text-teal-600 dark:bg-teal-900/50 dark:text-teal-400">
              {connectedDocCount} doc{connectedDocCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-teal-500 !border-teal-700" />
    </>
  );
}

// ─── Area Node (container / subflow) ──────────────────────────────────────
// ─────────────────────────────────────────────
// MODEL NODE — orange/copper, inline-editable label
// Represents a named model concept (e.g. "Pump", "Heat Exchanger")
// that bridges documents to FMU parameters
// ─────────────────────────────────────────────
export interface ModelNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  onUpdateLabel?: (nodeId: string, label: string) => void;
}

export function ModelNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, onUpdateLabel } = data as ModelNodeData;
  const label = node.model_label || node.title || "Model";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);
  const inputRef = React.useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(label); }, [label]);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  const commit = () => {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed && trimmed !== label) {
      onUpdateLabel?.(node.id, trimmed);
    } else {
      setDraft(label);
    }
  };

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-orange-500 !border-orange-700" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-orange-500 !border-orange-700" />
      <div
        className="relative flex flex-col justify-center rounded-2xl border-[3px] border-orange-400 dark:border-orange-500 bg-white dark:bg-neutral-900 shadow-md select-none transition-all hover:shadow-lg"
        style={{ width: '100%', height: '100%' }}
        onDoubleClick={() => setEditing(true)}
      >
        <div className="flex items-center gap-2.5 px-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-300">
            <Cpu size={16} />
          </div>
          <div className="flex-1 min-w-0">
            {editing ? (
              <input
                ref={inputRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit();
                  if (e.key === "Escape") { setDraft(label); setEditing(false); }
                }}
                className="w-full bg-transparent text-sm font-semibold text-orange-900 dark:text-orange-100 outline-none border-b-2 border-orange-300 dark:border-orange-600 py-0.5"
                autoFocus
              />
            ) : (
              <p className="text-sm font-semibold text-orange-900 dark:text-orange-100 leading-snug truncate">
                {label}
              </p>
            )}
          </div>
        </div>
        {!editing && (
          <div className="absolute bottom-1.5 right-3">
            <span className="text-[9px] font-medium tracking-wide uppercase text-orange-400 dark:text-orange-500">
              model
            </span>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} id="right" className="!bg-orange-500 !border-orange-700" />
      <Handle type="source" position={Position.Bottom} className="!bg-orange-500 !border-orange-700" />
    </>
  );
}

// ─────────────────────────────────────────────
// Shared inline-edit hook for shape nodes
// ─────────────────────────────────────────────
function useInlineEdit(
  initialText: string,
  nodeId: string,
  onUpdateText?: (id: string, text: string) => void,
) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(initialText);
  const ref = React.useRef<HTMLDivElement>(null);

  useEffect(() => { setDraft(initialText); }, [initialText]);
  useEffect(() => {
    if (editing && ref.current) {
      ref.current.focus();
      // place cursor at end
      const sel = window.getSelection();
      if (sel && ref.current.childNodes.length) {
        sel.selectAllChildren(ref.current);
        sel.collapseToEnd();
      }
    }
  }, [editing]);

  const commit = () => {
    setEditing(false);
    const text = ref.current?.innerText?.trim() ?? "";
    if (text !== initialText) {
      onUpdateText?.(nodeId, text);
    }
  };

  return { editing, setEditing, draft, setDraft, ref, commit };
}

// ─── SQUARE SHAPE NODE ──────────────────────────────────────────────
export interface SquareShapeNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  onUpdateText?: (id: string, text: string) => void;
}

export function SquareShapeNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, onUpdateText } = data as SquareShapeNodeData;
  const { editing, setEditing, ref, commit } = useInlineEdit(node.text || node.title || "", node.id, onUpdateText);

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-neutral-400 !border-neutral-500" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-neutral-400 !border-neutral-500" />
      <div
        className="flex items-center justify-center rounded-md border-2 border-neutral-400 dark:border-neutral-500 bg-white dark:bg-neutral-900 shadow-sm select-none"
        style={{ width: '100%', height: '100%' }}
        onDoubleClick={() => setEditing(true)}
      >
        <div
          ref={ref}
          contentEditable={editing}
          suppressContentEditableWarning
          onBlur={commit}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") { commit(); }
          }}
          className={`text-sm text-center text-neutral-800 dark:text-neutral-200 outline-none max-w-[90%] break-words ${
            editing ? "cursor-text" : "cursor-default"
          }`}
        >
          {node.text || node.title || ""}
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="right" className="!bg-neutral-400 !border-neutral-500" />
      <Handle type="source" position={Position.Bottom} className="!bg-neutral-400 !border-neutral-500" />
    </>
  );
}

// ─── CIRCLE SHAPE NODE ──────────────────────────────────────────────
export interface CircleShapeNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  onUpdateText?: (id: string, text: string) => void;
}

export function CircleShapeNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, onUpdateText } = data as CircleShapeNodeData;
  const { editing, setEditing, ref, commit } = useInlineEdit(node.text || node.title || "", node.id, onUpdateText);

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-neutral-400 !border-neutral-500" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-neutral-400 !border-neutral-500" />
      <div
        className="flex items-center justify-center rounded-full border-2 border-neutral-400 dark:border-neutral-500 bg-white dark:bg-neutral-900 shadow-sm select-none"
        style={{ width: '100%', height: '100%' }}
        onDoubleClick={() => setEditing(true)}
      >
        <div
          ref={ref}
          contentEditable={editing}
          suppressContentEditableWarning
          onBlur={commit}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") { commit(); }
          }}
          className={`text-sm text-center text-neutral-800 dark:text-neutral-200 outline-none max-w-[70%] break-words ${
            editing ? "cursor-text" : "cursor-default"
          }`}
        >
          {node.text || node.title || ""}
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="right" className="!bg-neutral-400 !border-neutral-500" />
      <Handle type="source" position={Position.Bottom} className="!bg-neutral-400 !border-neutral-500" />
    </>
  );
}

// ─── DIAMOND SHAPE NODE ─────────────────────────────────────────────
export interface DiamondShapeNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  onUpdateText?: (id: string, text: string) => void;
}

export function DiamondShapeNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, onUpdateText } = data as DiamondShapeNodeData;
  const { editing, setEditing, ref, commit } = useInlineEdit(node.text || node.title || "", node.id, onUpdateText);

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-neutral-400 !border-neutral-500" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-neutral-400 !border-neutral-500" />
      <div
        className="relative select-none"
        style={{ width: '100%', height: '100%' }}
        onDoubleClick={() => setEditing(true)}
      >
        <div
          className="absolute inset-0 border-2 border-neutral-400 dark:border-neutral-500 bg-white dark:bg-neutral-900 shadow-sm"
          style={{ clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" }}
        />
        <div className="absolute inset-0 flex items-center justify-center px-[25%]">
          <div
            ref={ref}
            contentEditable={editing}
            suppressContentEditableWarning
            onBlur={commit}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Escape") { commit(); }
            }}
            className={`text-sm text-center text-neutral-800 dark:text-neutral-200 outline-none break-words ${
              editing ? "cursor-text" : "cursor-default"
            }`}
          >
            {node.text || node.title || ""}
          </div>
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="right" className="!bg-neutral-400 !border-neutral-500" />
      <Handle type="source" position={Position.Bottom} className="!bg-neutral-400 !border-neutral-500" />
    </>
  );
}

// ─── NOTE NODE (Sticky Note) ────────────────────────────────────────
export interface NoteNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  onUpdateText?: (id: string, text: string) => void;
}

export function NoteNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, onUpdateText } = data as NoteNodeData;
  const { editing, setEditing, ref, commit } = useInlineEdit(node.text || "", node.id, onUpdateText);

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-amber-400 !border-amber-500" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-amber-400 !border-amber-500" />
      <div
        className="flex flex-col rounded-sm bg-amber-100 dark:bg-amber-900/60 shadow-[2px_3px_8px_rgba(0,0,0,0.12)] select-none"
        style={{ width: '100%', height: '100%' }}
        onDoubleClick={() => setEditing(true)}
      >
        {/* Fold corner */}
        <div className="absolute top-0 right-0 w-5 h-5 bg-amber-200 dark:bg-amber-800"
          style={{ clipPath: "polygon(100% 0%, 0% 0%, 100% 100%)" }}
        />
        <div
          ref={ref}
          contentEditable={editing}
          suppressContentEditableWarning
          onBlur={commit}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") { commit(); }
          }}
          className={`flex-1 p-3 text-sm text-amber-900 dark:text-amber-100 outline-none break-words whitespace-pre-wrap ${
            editing ? "cursor-text" : "cursor-default"
          }`}
        >
          {node.text || ""}
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="right" className="!bg-amber-400 !border-amber-500" />
      <Handle type="source" position={Position.Bottom} className="!bg-amber-400 !border-amber-500" />
    </>
  );
}

// ─── RICH TEXT NODE ──────────────────────────────────────────────────
const TEXT_FORMATS = [
  { label: "H1", tag: "h1", className: "text-2xl font-bold" },
  { label: "H2", tag: "h2", className: "text-xl font-semibold" },
  { label: "H3", tag: "h3", className: "text-base font-semibold" },
  { label: "P", tag: "p", className: "text-sm" },
] as const;

export interface RichTextNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  onUpdateText?: (id: string, text: string) => void;
}

export function RichTextNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, onUpdateText } = data as RichTextNodeData;
  const [editing, setEditing] = useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing && ref.current) {
      ref.current.focus();
      const sel = window.getSelection();
      if (sel && ref.current.childNodes.length) {
        sel.selectAllChildren(ref.current);
        sel.collapseToEnd();
      }
    }
  }, [editing]);

  const commit = () => {
    setEditing(false);
    const html = ref.current?.innerHTML ?? "";
    if (html !== (node.text || "")) {
      onUpdateText?.(node.id, html);
    }
  };

  const applyFormat = (tag: string) => {
    document.execCommand("formatBlock", false, tag);
  };

  const toggleStyle = (cmd: string) => {
    document.execCommand(cmd, false);
  };

  return (
    <>
      {/* Actions toolbar (color + delete) */}

      {/* Format toolbar — only visible when editing */}
      {editing && (
        <NodeToolbar isVisible position={Position.Top} align="center" offset={40}>
          <div className="flex items-center gap-0.5 px-2 py-1 rounded-lg bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 shadow-lg">
            {TEXT_FORMATS.map(f => (
              <button
                key={f.label}
                onMouseDown={(e) => { e.preventDefault(); applyFormat(f.tag); }}
                className="px-1.5 py-0.5 text-xs font-medium rounded hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
              >
                {f.label}
              </button>
            ))}
            <div className="w-px h-4 bg-neutral-200 dark:bg-neutral-600 mx-0.5" />
            <button
              onMouseDown={(e) => { e.preventDefault(); toggleStyle("bold"); }}
              className="px-1.5 py-0.5 text-xs font-bold rounded hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
            >
              B
            </button>
            <button
              onMouseDown={(e) => { e.preventDefault(); toggleStyle("italic"); }}
              className="px-1.5 py-0.5 text-xs italic rounded hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
            >
              I
            </button>
          </div>
        </NodeToolbar>
      )}
      <Handle type="target" position={Position.Top} className="!bg-neutral-400 !border-neutral-500" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-neutral-400 !border-neutral-500" />
      <div
        className="select-none"
        style={{ width: '100%', height: '100%' }}
        onDoubleClick={() => setEditing(true)}
      >
        <div
          ref={ref}
          contentEditable={editing}
          suppressContentEditableWarning
          onBlur={commit}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") { commit(); }
          }}
          className={`h-full w-full p-2 text-neutral-800 dark:text-neutral-200 outline-none break-words prose prose-sm dark:prose-invert max-w-none
            prose-p:my-0.5 prose-headings:my-0.5 prose-headings:leading-snug ${
            editing ? "cursor-text" : "cursor-default"
          }`}
          dangerouslySetInnerHTML={!editing ? { __html: node.text || "" } : undefined}
        />
      </div>
      <Handle type="source" position={Position.Right} id="right" className="!bg-neutral-400 !border-neutral-500" />
      <Handle type="source" position={Position.Bottom} className="!bg-neutral-400 !border-neutral-500" />
    </>
  );
}

export interface AreaNodeData extends Record<string, unknown> {
  node: CanvasNodeData;
  onDelete?: (id: string) => void;
  onSetColor?: (id: string, color: string) => void;
  connectedSourceNames: string[];
  highlighted?: boolean;
}

export function AreaNode({ data }: NodeProps) {
  const { node, onDelete, onSetColor, connectedSourceNames, highlighted } = data as AreaNodeData;
  const label = node.area_label || "Area";

  return (
    <>

      <Handle type="target" position={Position.Top} className="!bg-indigo-400 !border-indigo-600" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-indigo-400 !border-indigo-600" />
      <Handle type="target" position={Position.Right} id="right" className="!bg-indigo-400 !border-indigo-600" />
      <div
        className={`w-full h-full rounded-2xl border-[3px] border-dashed transition-all ${
          highlighted
            ? "border-indigo-500 dark:border-indigo-400 bg-indigo-100/55 dark:bg-indigo-900/35 shadow-[0_0_0_4px_rgba(99,102,241,0.12)]"
            : "border-indigo-300 dark:border-indigo-700 bg-indigo-50/30 dark:bg-indigo-950/15"
        }`}
      >
        <div className="absolute top-2 left-3 flex items-center gap-1.5">
          <span className="text-[11px] font-semibold text-indigo-500 dark:text-indigo-400">
            {label}
          </span>
          {connectedSourceNames.length > 0 && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/50 text-indigo-500 dark:text-indigo-400">
              {connectedSourceNames.length} source{connectedSourceNames.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-400 !border-indigo-600" />
    </>
  );
}
