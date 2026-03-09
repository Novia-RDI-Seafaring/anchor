"use client";

import React, { useState, useEffect, useRef } from "react";
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";

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

// Overlay for a single bbox highlight.
// Coordinates are PDF points (BOTTOMLEFT origin). We use % positioning so it
// works regardless of the rendered image size — as long as we know the natural
// page size in points. We approximate standard A4 (595×842 pt) if unknown.
function BboxOverlays({
  highlights,
  pageWidth,
  pageHeight,
}: {
  highlights: PDFHighlight[];
  pageWidth: number;
  pageHeight: number;
}) {
  return (
    <>
      {highlights.map((h, i) => {
        const [l = 0, t = 0, r = 0, b = 0] = h.bbox;
        if (!r && !b) return null; // skip empty bbox
        const leftPct   = (l / pageWidth)  * 100;
        const topPct    = ((pageHeight - b) / pageHeight) * 100;
        const widthPct  = ((r - l) / pageWidth)  * 100;
        const heightPct = ((b - t) / pageHeight) * 100;
        return (
          <div
            key={i}
            className="pointer-events-none absolute rounded-sm"
            style={{
              left:   `${leftPct}%`,
              top:    `${topPct}%`,
              width:  `${widthPct}%`,
              height: `${heightPct}%`,
              border: "2.5px solid rgba(99,102,241,0.85)",
              backgroundColor: "rgba(99,102,241,0.12)",
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
  const [numPages, setNumPages]     = useState(0);
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [scale, setScale]           = useState(1.0);
  // Natural dimensions of the current page screenshot (for bbox overlay %)
  const [imgSize, setImgSize]       = useState<{ w: number; h: number } | null>(null);
  const sidebarRef                  = useRef<HTMLDivElement>(null);

  // Fetch page count once
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

  // Scroll sidebar thumbnail into view
  useEffect(() => {
    sidebarRef.current
      ?.querySelector(`[data-page="${currentPage}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [currentPage]);

  const highlightsOnPage = highlights.filter((h) => h.page === currentPage);

  // We receive PDF-point coordinates. The screenshot renders at the server's
  // natural resolution. The only info we have is the rendered image pixel size,
  // captured via onLoad. We approximate the page dimensions in points using the
  // image's aspect ratio × 595 pt (A4 width), which is correct for most docs.
  // For precise overlays the server would need to return page dimensions, but
  // this gives a good-enough result without extra roundtrips.
  const pageWidthPt  = imgSize ? 595 : 595;
  const pageHeightPt = imgSize ? 595 * (imgSize.h / imgSize.w) : 842;

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
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={screenshotUrl(filename, pg)}
                alt={`Page ${pg}`}
                className="w-full h-auto block"
                loading="lazy"
              />
              <span className="text-[10px] text-neutral-500 dark:text-neutral-400 mt-0.5">{pg}</span>
            </button>
          ))}
        </div>

        {/* ── Main content ── */}
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
                {currentPage} / {numPages || "…"}
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

          {/* Page viewer */}
          <div className="flex-1 overflow-auto bg-neutral-300 dark:bg-neutral-950 flex justify-center p-6">
            <div
              className="relative inline-block shadow-2xl"
              style={{ transform: `scale(${scale})`, transformOrigin: "top center" }}
            >
              {/* Full-page screenshot */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                key={`${filename}-${currentPage}`}
                src={screenshotUrl(filename, currentPage)}
                alt={`Page ${currentPage}`}
                className="block max-w-none"
                style={{ display: "block" }}
                onLoad={(e) => {
                  const img = e.currentTarget;
                  setImgSize({ w: img.naturalWidth, h: img.naturalHeight });
                }}
              />
              {/* Bbox highlight overlays */}
              {highlightsOnPage.length > 0 && imgSize && (
                <BboxOverlays
                  highlights={highlightsOnPage}
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
