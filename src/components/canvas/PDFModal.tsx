"use client";

import React, { useState, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";

if (typeof window !== "undefined") {
  pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
}

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

export interface PDFHighlight {
  page: number;
  bbox: number[]; // [l, t, r, b] in PDF points, BOTTOMLEFT origin
}

interface PDFModalProps {
  filename: string;
  initialPage: number;
  highlights?: PDFHighlight[];
  onClose: () => void;
}

interface PageSize {
  width: number;  // PDF points
  height: number; // PDF points
}

function BboxOverlay({ highlights, pageSize, scale }: {
  highlights: PDFHighlight[];
  pageSize: PageSize | null;
  scale: number;
}) {
  if (!pageSize) return null;
  return (
    <>
      {highlights.map((h, i) => {
        const [l = 0, t = 0, r = 0, b = 0] = h.bbox;
        // BOTTOMLEFT origin → CSS top-left origin
        const leftPct = (l / pageSize.width) * 100;
        const topPct = ((pageSize.height - b) / pageSize.height) * 100;
        const widthPct = ((r - l) / pageSize.width) * 100;
        const heightPct = ((b - t) / pageSize.height) * 100;
        return (
          <div
            key={i}
            className="pointer-events-none absolute rounded-sm"
            style={{
              left: `${leftPct}%`,
              top: `${topPct}%`,
              width: `${widthPct}%`,
              height: `${heightPct}%`,
              border: "2px solid rgba(99, 102, 241, 0.85)",
              backgroundColor: "rgba(99, 102, 241, 0.13)",
            }}
          />
        );
      })}
    </>
  );
}

export function PDFModal({ filename, initialPage, highlights = [], onClose }: PDFModalProps) {
  const pdfUrl = `${API_URL}/api/documents/pdf/serve?filename=${encodeURIComponent(filename)}`;
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [scale, setScale] = useState(1.0);
  const [pageSize, setPageSize] = useState<PageSize | null>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);

  const highlightsByPage = highlights.reduce<Record<number, PDFHighlight[]>>((acc, h) => {
    (acc[h.page] ??= []).push(h);
    return acc;
  }, {});

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Scroll sidebar thumbnail into view when page changes
  useEffect(() => {
    const el = sidebarRef.current?.querySelector(`[data-page="${currentPage}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [currentPage]);

  return (
    <div
      className="fixed inset-0 z-[100] flex bg-black/75 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative flex w-full max-w-6xl mx-auto my-4 bg-white dark:bg-neutral-900 rounded-2xl overflow-hidden shadow-2xl"
        style={{ maxHeight: "calc(100vh - 2rem)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <Document
          file={pdfUrl}
          onLoadSuccess={({ numPages }) => setNumPages(numPages)}
          loading={null}
        >
          {/* Left sidebar: page thumbnails */}
          <div
            ref={sidebarRef}
            className="w-28 shrink-0 bg-neutral-100 dark:bg-neutral-950 border-r border-neutral-200 dark:border-neutral-800 overflow-y-auto flex flex-col p-2 gap-1"
          >
            <p className="text-[10px] text-neutral-400 uppercase tracking-wide text-center mb-1">Pages</p>
            {Array.from({ length: numPages }, (_, i) => i + 1).map((pg) => (
              <button
                key={pg}
                data-page={pg}
                onClick={() => setCurrentPage(pg)}
                className={`w-full rounded-lg overflow-hidden border-2 transition-all flex flex-col items-center pb-0.5 ${
                  currentPage === pg
                    ? "border-indigo-500 shadow-md"
                    : "border-transparent hover:border-neutral-300 dark:hover:border-neutral-600"
                }`}
              >
                <Page
                  pageNumber={pg}
                  width={96}
                  renderAnnotationLayer={false}
                  renderTextLayer={false}
                  loading={
                    <div className="w-24 h-32 bg-neutral-200 dark:bg-neutral-800 animate-pulse rounded" />
                  }
                />
                <span className="text-[10px] text-neutral-500 dark:text-neutral-400 mt-0.5">{pg}</span>
              </button>
            ))}
          </div>

          {/* Main content */}
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-neutral-200 dark:border-neutral-800 shrink-0">
              <span className="text-sm font-medium text-neutral-800 dark:text-white truncate max-w-xs">
                {filename}
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage <= 1}
                  className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-30"
                >
                  <ChevronLeft size={15} />
                </button>
                <span className="text-sm text-neutral-600 dark:text-neutral-300 tabular-nums w-20 text-center">
                  {currentPage} / {numPages}
                </span>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(numPages, p + 1))}
                  disabled={currentPage >= numPages}
                  className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-30"
                >
                  <ChevronRight size={15} />
                </button>
                <div className="w-px h-4 bg-neutral-200 dark:bg-neutral-700 mx-1" />
                <button
                  onClick={() => setScale((s) => Math.max(0.4, +(s - 0.2).toFixed(1)))}
                  className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  <ZoomOut size={15} />
                </button>
                <span className="text-xs text-neutral-500 w-10 text-center tabular-nums">
                  {Math.round(scale * 100)}%
                </span>
                <button
                  onClick={() => setScale((s) => Math.min(3, +(s + 0.2).toFixed(1)))}
                  className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  <ZoomIn size={15} />
                </button>
                <div className="w-px h-4 bg-neutral-200 dark:bg-neutral-700 mx-1" />
                <button
                  onClick={onClose}
                  className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500"
                >
                  <X size={15} />
                </button>
              </div>
            </div>

            {/* PDF page */}
            <div className="flex-1 overflow-auto bg-neutral-300 dark:bg-neutral-950 flex justify-center p-6">
              <div className="relative inline-block shadow-2xl">
                <Page
                  pageNumber={currentPage}
                  scale={scale}
                  renderAnnotationLayer={false}
                  renderTextLayer={false}
                  onLoadSuccess={(page) =>
                    setPageSize({ width: page.originalWidth, height: page.originalHeight })
                  }
                  loading={
                    <div
                      className="bg-white dark:bg-neutral-800 animate-pulse"
                      style={{ width: 595 * scale, height: 842 * scale }}
                    />
                  }
                />
                <BboxOverlay
                  highlights={highlightsByPage[currentPage] ?? []}
                  pageSize={pageSize}
                  scale={scale}
                />
              </div>
            </div>
          </div>
        </Document>
      </div>
    </div>
  );
}
