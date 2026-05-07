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

function screenshotUrl(filename: string, page: number, highlight?: PDFHighlight | null): string {
  const params = new URLSearchParams({
    filename,
    page_no: String(page),
  });
  if (highlight && Array.isArray(highlight.bbox) && highlight.bbox.length === 4) {
    const [l = 0, t = 0, r = 0, b = 0] = highlight.bbox;
    params.set("bbox_l", String(l));
    params.set("bbox_t", String(t));
    params.set("bbox_r", String(r));
    params.set("bbox_b", String(b));
    params.set("draw_bbox", "true");
  }
  return `${API_URL}/api/documents/pdf/screenshot?${params.toString()}`;
}

export function PDFModal({
  filename,
  initialPage,
  highlights = [],
  onClose,
}: PDFModalProps) {
  const fallbackPageCount = Math.max(
    initialPage,
    ...highlights.map((highlight) => highlight.page),
    1,
  );
  const [numPages, setNumPages] = useState(fallbackPageCount);
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [scale, setScale] = useState(1.0);
  const [pageImageMode, setPageImageMode] = useState<"highlight" | "plain" | "error">(
    highlights.length > 0 ? "highlight" : "plain"
  );

  // Index of the "active" (focused) highlight. Null = just browsing pages freely.
  const [activeHlIdx, setActiveHlIdx] = useState<number | null>(() => {
    if (highlights.length === 0) return null;
    const idx = highlights.findIndex((h) => h.page === initialPage);
    return idx >= 0 ? idx : 0;
  });

  const sidebarRef = useRef<HTMLDivElement>(null);

  // Fetch total page count once when the modal first opens for this filename.
  // Do NOT include currentPage — re-fetching on every page turn causes race conditions
  // that can overwrite the correct count with a stale response.
  useEffect(() => {
    let cancelled = false;
    const fetchInfo = (attempt: number) => {
      fetch(`${API_URL}/api/documents/pdf/info?filename=${encodeURIComponent(filename)}&page_no=1`)
        .then((r) => {
          if (!r.ok) throw new Error(`PDF info failed: ${r.status}`);
          return r.json();
        })
        .then((d) => {
          if (cancelled) return;
          const count = typeof d.page_count === "number" && d.page_count > 0
            ? d.page_count
            : fallbackPageCount;
          if (count <= 1 && attempt < 2) {
            // Page count of 1 may indicate a transient read — retry once
            setTimeout(() => fetchInfo(attempt + 1), 300);
          } else {
            setNumPages(Math.max(count, fallbackPageCount));
          }
        })
        .catch(() => {
          if (cancelled) return;
          if (attempt < 2) {
            setTimeout(() => fetchInfo(attempt + 1), 300);
          } else {
            setNumPages(fallbackPageCount);
          }
        });
    };
    fetchInfo(0);
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
  const activeHighlight =
    activeHlIdx !== null && highlights[activeHlIdx]?.page === currentPage
      ? highlights[activeHlIdx]
      : highlightsOnPage[0] ?? null;

  useEffect(() => {
    setPageImageMode(activeHighlight ? "highlight" : "plain");
  }, [filename, currentPage, activeHighlight]);

  const hasHighlights = highlights.length > 0;
  const pageImageSrc =
    pageImageMode === "highlight" && activeHighlight
      ? screenshotUrl(filename, currentPage, activeHighlight)
      : screenshotUrl(filename, currentPage);
  const rawPdfUrl = `${API_URL}/api/documents/pdf/serve?filename=${encodeURIComponent(filename)}`;

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
                className={`w-full rounded-lg overflow-hidden border-2 transition-all flex flex-col items-center pb-0.5 ${currentPage === pg
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
                  onError={(e) => {
                    const el = e.currentTarget;
                    el.style.display = "none";
                    const placeholder = el.nextElementSibling as HTMLElement | null;
                    if (placeholder) placeholder.style.display = "flex";
                  }}
                />
                <div
                  className="w-full aspect-[3/4] bg-neutral-200 dark:bg-neutral-800 items-center justify-center text-neutral-400 text-xs"
                  style={{ display: "none" }}
                >
                  ?
                </div>
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
                    className={`shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded-full transition-colors ${i === activeHlIdx
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
              {pageImageMode === "error" ? (
                <div className="flex min-h-[420px] w-[720px] max-w-full items-center justify-center rounded bg-white px-8 text-center">
                  <div className="space-y-3">
                    <p className="text-sm text-neutral-600">
                      PDF preview failed for this page.
                    </p>
                    <a
                      href={rawPdfUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex rounded-md bg-neutral-900 px-3 py-2 text-sm text-white hover:bg-neutral-700"
                    >
                      Open Raw PDF
                    </a>
                  </div>
                </div>
              ) : (
                <img
                  key={`${filename}-${currentPage}-${pageImageMode}-${activeHlIdx ?? "none"}`}
                  src={pageImageSrc}
                  alt={`Page ${currentPage}`}
                  className="block max-w-none"
                  onError={() => {
                    if (pageImageMode === "highlight" && activeHighlight) {
                      setPageImageMode("plain");
                      return;
                    }
                    setPageImageMode("error");
                  }}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
