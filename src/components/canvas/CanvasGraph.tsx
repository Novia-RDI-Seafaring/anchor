"use client";

import React, { useState, useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Network } from "lucide-react";
import dynamic from "next/dynamic";
import { NoteNode, type NoteNodeData, type NoteData } from "./NoteNode";
import type { PDFHighlight } from "./PDFModal";

// Dynamically import PDFModal so pdfjs-dist never runs during SSR
const PDFModal = dynamic(
  () => import("./PDFModal").then((m) => m.PDFModal),
  { ssr: false }
);

// --- Types ---
interface Relation {
  from_id: string;
  to_id: string;
  label: string;
}

interface CanvasState {
  notes: NoteData[];
  relations: Relation[];
}

interface PDFModalState {
  filename: string;
  page: number;
  highlights: PDFHighlight[];
}

// --- Layout constants ---
const COLS = 3;
const COL_W = 300;
const ROW_H = 180;

const nodeTypes: NodeTypes = { noteNode: NoteNode };

interface CanvasGraphProps {
  canvas: CanvasState | null | undefined;
}

export function CanvasGraph({ canvas }: CanvasGraphProps) {
  const [pdfModal, setPdfModal] = useState<PDFModalState | null>(null);

  const handleOpenPDF = useCallback(
    (filename: string, page: number, highlights: PDFHighlight[]) => {
      setPdfModal({ filename, page, highlights });
    },
    []
  );

  const notes = canvas?.notes ?? [];
  const relations = canvas?.relations ?? [];

  const nodes: Node[] = useMemo(
    () =>
      notes.map((note, idx) => ({
        id: note.id || `note-${idx}`,
        type: "noteNode",
        position: {
          x: (idx % COLS) * COL_W,
          y: Math.floor(idx / COLS) * ROW_H,
        },
        data: {
          note: { ...note, id: note.id || `note-${idx}` },
          onOpenPDF: handleOpenPDF,
        } satisfies NoteNodeData,
      })),
    [notes, handleOpenPDF]
  );

  const edges: Edge[] = useMemo(
    () =>
      relations.map((rel, idx) => ({
        id: `edge-${idx}`,
        source: rel.from_id,
        target: rel.to_id,
        label: rel.label || undefined,
        type: "smoothstep",
        animated: true,
        style: { stroke: "#6366f1", strokeWidth: 2 },
        labelStyle: { fill: "#6366f1", fontWeight: 500, fontSize: 11 },
        labelBgStyle: { fill: "#f5f3ff", fillOpacity: 0.9 },
        labelBgPadding: [4, 2] as [number, number],
      })),
    [relations]
  );

  if (notes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="h-16 w-16 rounded-2xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center mb-4">
          <Network size={28} className="text-neutral-400 dark:text-neutral-500" />
        </div>
        <h3 className="text-base font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
          Canvas is empty
        </h3>
        <p className="text-sm text-neutral-400 dark:text-neutral-500 max-w-xs">
          Ask the agent to research a topic and build connections — notes will
          appear as a knowledge graph here.
        </p>
      </div>
    );
  }

  return (
    <>
      <div
        className="w-full rounded-xl border border-neutral-200 dark:border-neutral-800 overflow-hidden"
        style={{ height: "calc(100vh - 260px)", minHeight: 400 }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.2}
          maxZoom={2.5}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1.2}
            className="!bg-neutral-50 dark:!bg-neutral-950"
            color="currentColor"
          />
          <Controls className="!bg-white dark:!bg-neutral-900 !border-neutral-200 dark:!border-neutral-800 !shadow-sm" />
          <MiniMap
            className="!bg-white dark:!bg-neutral-900 !border-neutral-200 dark:!border-neutral-800"
            nodeStrokeColor="#6366f1"
            nodeColor="#e0e7ff"
            maskColor="rgba(0,0,0,0.06)"
          />
        </ReactFlow>
      </div>

      {pdfModal && (
        <PDFModal
          filename={pdfModal.filename}
          initialPage={pdfModal.page}
          highlights={pdfModal.highlights}
          onClose={() => setPdfModal(null)}
        />
      )}
    </>
  );
}
