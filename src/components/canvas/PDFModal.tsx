"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, MapPin } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

export interface PDFHighlight {
  page: number;
  bbox: number[]; // [l, t, r, b] — PDF points, BOTTOMLEFT origin
}

interface PDFModalProps {
  filename: string;
  initialPage: number;
  highlights?: PDFHighlight[];
  onClose: () => void;
}

function screenshotUrl(filename: string, page: number): string {
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}`;
}

// Bbox overlays on the current page.
// activeIdx: index into `highlights` array of the currently-focused highlight
// (shown in amber); all others shown in indigo at lower opacity.
function BboxOverlays({
  highlights,
  activeIdx,
  pageWidth,
  pageHeight,
}: {
  highlights: PDFHighlight[];
  activeIdx: number | null;
  pageWidth: number;
  pageHeight: number;
}) {
  return (
    <>
      {highlights.map((h, i) => {
        const [l = 0, t = 0, r = 0, b = 0] = h.bbox;
        if (!r && !b) return null;
        const isActive = i === activeIdx;
        const leftPct   = (l / pageWidth)  * 100;
        const topPct    = ((pageHeight - b) / pageHeight) * 100;
        const widthPct  = ((r - l) / pageWidth)  * 100;
        const heightPct = ((b - t) / pageHeight) * 100;
        return (
          <div
            key={i}
            className="pointer-events-none absolute rounded-sm transition-colors"
            style={{
              left:   `${leftPct}%`,
              top:    `${topPct}%`,
              width:  `${widthPct}%`,
              height: `${heightPct}%`,
              border: isActive
                ? "2.5px solid rgba(245,158,11,0.95)"
                : "2px solid rgba(99,102,241,0.6)",
              backgroundColor: isActive
                ? "rgba(245,158,11,0.15)"
                : "rgba(99,102,241,0.08)",
              zIndex: isActive ? 2 : 1,
            }}
          />
        );
      })}
    </>
  );
}

export function PDFModal({
  filename,
  initialPage,
  highlights = [],
  onClose,
}: PDFModalProps) {
  const [numPages, setNumPages]       = useState(0);
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [scale, setScale]             = useState(1.0);
  const [imgSize, setImgSize]         = useState<{ w: number; h: number } | null>(null);

  // Index of the "active" (focused) highlight. Null = just browsing pages freely.
  const [activeHlIdx, setActiveHlIdx] = useState<number | null>(() => {
    if (highlights.length === 0) return null;
    const idx = highlights.findIndex((h) => h.page === initialPage);
    return idx >= 0 ? idx : 0;
  });

  const sidebarRef = useRef<HTMLDivElement>(null);

  // Fetch page count
  useEffect(() => {
    fetch(`${API_URL}/api/documents/pdf/info?filename=${encodeURIComponent(filename)}`)
      .then((r) => r.json())
      .then((d) => setNumPages(d.page_count ?? 0))
      .catch(() => setNumPages(1));
  }, [filename]);

  // Close on Escape
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  // Scroll sidebar into view when currentPage changes
  useEffect(() => {
    sidebarRef.current
      ?.querySelector(`[data-page="${currentPage}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [currentPage]);

  // Jump to a highlight's page and make it active
  const goToHighlight = useCallback((idx: number) => {
    if (idx < 0 || idx >= highlights.length) return;
    setActiveHlIdx(idx);
    setCurrentPage(highlights[idx]!.page);
  }, [highlights]);

  const highlightsOnPage = highlights.filter((h) => h.page === currentPage);
  // Map global highlight index → per-page overlay index
  const activeHlIdxOnPage = activeHlIdx !== null && highlights[activeHlIdx]?.page === currentPage
    ? highlightsOnPage.indexOf(highlights[activeHlIdx])
    : null;

  // Page dimensions in PDF points — approximated from image aspect ratio × 595pt (A4 width)
  const pageWidthPt  = 595;
  const pageHeightPt = imgSize ? 595 * (imgSize.h / imgSize.w) : 842;

  const hasHighlights = highlights.length > 0;

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
        {/* ── Left sidebar: page thumbnails ── */}
        <div
          ref={sidebarRef}
          className="w-28 shrink-0 bg-neutral-100 dark:bg-neutral-950 border-r border-neutral-200 dark:border-neutral-800 overflow-y-auto flex flex-col p-2 gap-1"
        >
          <p className="text-[10px] text-neutral-400 uppercase tracking-wide text-center mb-1">Pages</p>
          {Array.from({ length: numPages }, (_, i) => i + 1).map((pg) => {
            const hasHL = highlights.some((h) => h.page === pg);
            return (
              <button
                key={pg}
                data-page={pg}
                onClick={() => { setCurrentPage(pg); setActiveHlIdx(null); }}
                className={`w-full rounded-lg overflow-hidden border-2 transition-all flex flex-col items-center pb-0.5 ${
                  currentPage === pg
                    ? "border-indigo-500 shadow-md"
                    : "border-transparent hover:border-neutral-300 dark:hover:border-neutral-600"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={screenshotUrl(filename, pg)}
                  alt={`Page ${pg}`}
                  className="w-full h-auto block"
                  loading="lazy"
                />
                <div className="flex items-center gap-1 mt-0.5">
                  <span className="text-[10px] text-neutral-500 dark:text-neutral-400">{pg}</span>
                  {hasHL && (
                    <MapPin size={8} className="text-amber-500" />
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {/* ── Main content ── */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Toolbar */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-neutral-200 dark:border-neutral-800 shrink-0">
            <span className="text-sm font-medium text-neutral-800 dark:text-white truncate max-w-xs">
              {filename}
            </span>
            <div className="flex items-center gap-1.5">
              {/* Page navigation */}
              <button
                onClick={() => { setCurrentPage((p) => Math.max(1, p - 1)); setActiveHlIdx(null); }}
                disabled={currentPage <= 1}
                className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-30"
              >
                <ChevronLeft size={15} />
              </button>
              <span className="text-sm text-neutral-600 dark:text-neutral-300 tabular-nums w-20 text-center">
                {currentPage} / {numPages || "…"}
              </span>
              <button
                onClick={() => { setCurrentPage((p) => Math.min(numPages, p + 1)); setActiveHlIdx(null); }}
                disabled={currentPage >= numPages}
                className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-30"
              >
                <ChevronRight size={15} />
              </button>
              <div className="w-px h-4 bg-neutral-200 dark:bg-neutral-700 mx-1" />
              {/* Zoom */}
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
              <button onClick={onClose} className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">
                <X size={15} />
              </button>
            </div>
          </div>

          {/* Highlight navigation strip */}
          {hasHighlights && (
            <div className="flex items-center gap-2 px-4 py-1.5 border-b border-amber-100 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/25 shrink-0">
              <MapPin size={12} className="text-amber-500 shrink-0" />
              <span className="text-xs text-amber-700 dark:text-amber-400 font-medium">
                Highlights
              </span>
              <div className="flex items-center gap-1 ml-auto">
                <button
                  onClick={() => goToHighlight((activeHlIdx ?? 0) - 1)}
                  disabled={(activeHlIdx ?? 0) <= 0}
                  className="p-1 rounded hover:bg-amber-100 dark:hover:bg-amber-900/40 disabled:opacity-30 text-amber-700 dark:text-amber-400"
                >
                  <ChevronLeft size={13} />
                </button>
                <span className="text-xs text-amber-700 dark:text-amber-400 tabular-nums w-16 text-center">
                  {activeHlIdx !== null ? `${activeHlIdx + 1} / ${highlights.length}` : `— / ${highlights.length}`}
                </span>
                <button
                  onClick={() => goToHighlight((activeHlIdx ?? -1) + 1)}
                  disabled={activeHlIdx !== null && activeHlIdx >= highlights.length - 1}
                  className="p-1 rounded hover:bg-amber-100 dark:hover:bg-amber-900/40 disabled:opacity-30 text-amber-700 dark:text-amber-400"
                >
                  <ChevronRight size={13} />
                </button>
              </div>
              {/* Highlight pills — one per highlight, click to jump */}
              <div className="flex items-center gap-1 overflow-x-auto max-w-xs">
                {highlights.map((h, i) => (
                  <button
                    key={i}
                    onClick={() => goToHighlight(i)}
                    className={`shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded-full transition-colors ${
                      i === activeHlIdx
                        ? "bg-amber-400 dark:bg-amber-500 text-white"
                        : "bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-800"
                    }`}
                    title={`Page ${h.page}`}
                  >
                    p.{h.page}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Page viewer */}
          <div className="flex-1 overflow-auto bg-neutral-300 dark:bg-neutral-950 flex justify-center p-6">
            <div
              className="relative inline-block shadow-2xl"
              style={{ transform: `scale(${scale})`, transformOrigin: "top center" }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                key={`${filename}-${currentPage}`}
                src={screenshotUrl(filename, currentPage)}
                alt={`Page ${currentPage}`}
                className="block max-w-none"
                onLoad={(e) => {
                  const img = e.currentTarget;
                  setImgSize({ w: img.naturalWidth, h: img.naturalHeight });
                }}
              />
              {highlightsOnPage.length > 0 && imgSize && (
                <BboxOverlays
                  highlights={highlightsOnPage}
                  activeIdx={activeHlIdxOnPage}
                  pageWidth={pageWidthPt}
                  pageHeight={pageHeightPt}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
