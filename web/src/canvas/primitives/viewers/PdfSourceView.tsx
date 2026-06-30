import { useCallback, useEffect, useRef, useState } from "react";

import "pdfjs-dist/web/pdf_viewer.css";

import { documents } from "@/api/documents";
import { bboxToViewportRect, scrollOffsetForRect } from "@/lib/pdfHighlight";

import { loadPdf, pdfjs, type PdfDoc, type PdfViewport } from "./pdfjs";

/**
 * PdfSourceView — the real, selectable-text PDF viewer (#110a).
 *
 * Renders one page at a time with PDF.js: a canvas raster for crisp glyphs
 * plus an absolutely-positioned text layer so the user can select, copy, and
 * browser-find text. A grounded region bbox is drawn as a sharp SVG highlight
 * over the page and scrolled into view (deep-zoom). Page nav + zoom are driven
 * from the toolbar this component renders.
 *
 * This is the shared inner view used by both the docked split-screen pane and
 * the legacy modal quick-look. It owns no global state beyond the uiStore page
 * pointer passed down via props.
 */

const MIN_ZOOM = 0.4;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.2;

type Props = {
  slug: string;
  page: number;
  total: number;
  /** Region bbox to highlight (PDF points), applies only on `highlightPage`. */
  highlightBbox?: number[];
  highlightPage?: number;
  title?: string;
  onPageChange: (page: number) => void;
};

export function PdfSourceView({
  slug,
  page,
  total,
  highlightBbox,
  highlightPage,
  title,
  onPageChange,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const textLayerRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const docRef = useRef<PdfDoc | null>(null);
  const destroyRef = useRef<(() => Promise<void>) | null>(null);
  const renderTokenRef = useRef(0);

  const [zoom, setZoom] = useState(1);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState(total);
  // Bumped when a document finishes loading so the render effect re-fires.
  const [docReady, setDocReady] = useState(0);
  // Rendered page geometry, kept so the highlight overlay maps bbox -> pixels.
  const [viewportSize, setViewportSize] = useState<{ w: number; h: number } | null>(null);
  const [pageSize, setPageSize] = useState<{ w: number; h: number } | null>(null);

  // Load (and reload on slug change) the PDF document. One shared instance.
  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    setViewportSize(null);
    loadPdf(documents.pdfUrl(slug))
      .then(({ doc, destroy }) => {
        if (cancelled) {
          void destroy();
          return;
        }
        docRef.current = doc;
        destroyRef.current = destroy;
        setPageCount(doc.numPages);
        setDocReady((n) => n + 1);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load PDF");
        }
      });
    return () => {
      cancelled = true;
      docRef.current = null;
      const destroy = destroyRef.current;
      destroyRef.current = null;
      if (destroy) void destroy();
    };
  }, [slug]);

  const renderCurrentPage = useCallback(async () => {
    const doc = docRef.current;
    const canvas = canvasRef.current;
    const textLayerDiv = textLayerRef.current;
    if (!doc || !canvas || !textLayerDiv) return;
    if (page < 1 || page > doc.numPages) return;

    const token = ++renderTokenRef.current;
    const pdfPage = await doc.getPage(page);
    if (token !== renderTokenRef.current) return;

    const outputScale = window.devicePixelRatio || 1;
    const viewport: PdfViewport = pdfPage.getViewport({ scale: zoom });
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;

    const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;
    const renderTask = pdfPage.render({ canvas, canvasContext: ctx, viewport, transform });
    try {
      await renderTask.promise;
    } catch {
      return; // cancelled render
    }
    if (token !== renderTokenRef.current) return;

    // Text layer: clear, size to the rendered viewport, set the scale factor
    // CSS variables PDF.js' textLayer styles read, then render the text runs.
    textLayerDiv.replaceChildren();
    textLayerDiv.style.width = `${Math.floor(viewport.width)}px`;
    textLayerDiv.style.height = `${Math.floor(viewport.height)}px`;
    textLayerDiv.style.setProperty("--scale-factor", String(zoom));
    textLayerDiv.style.setProperty("--total-scale-factor", String(zoom));
    const textContentSource = pdfPage.streamTextContent();
    const textLayer = new pdfjs.TextLayer({
      textContentSource,
      container: textLayerDiv,
      viewport,
    });
    try {
      await textLayer.render();
    } catch {
      // text layer is best-effort; the canvas raster is the source of truth
    }

    if (token !== renderTokenRef.current) return;
    setViewportSize({ w: viewport.width, h: viewport.height });
    const [x0, y0, x1, y1] = pdfPage.view; // [x0, y0, x1, y1] in points
    setPageSize({ w: (x1 ?? 0) - (x0 ?? 0), h: (y1 ?? 0) - (y0 ?? 0) });
  }, [page, zoom]);

  // Re-render on page/zoom change and once the document has loaded.
  useEffect(() => {
    void renderCurrentPage();
  }, [renderCurrentPage, docReady]);

  // Deep-zoom: when the highlight targets the current page, scroll its bbox
  // into view once the page geometry is known.
  const highlightRect =
    highlightPage === page && pageSize && viewportSize
      ? bboxToViewportRect(highlightBbox, pageSize.w, pageSize.h, {
          width: viewportSize.w,
          height: viewportSize.h,
        })
      : null;

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || !highlightRect || !viewportSize) return;
    const offset = scrollOffsetForRect(
      highlightRect,
      scroller.clientWidth,
      scroller.clientHeight,
      viewportSize.w,
      viewportSize.h,
    );
    scroller.scrollTo({ left: offset.left, top: offset.top, behavior: "smooth" });
    // We intentionally depend on the rect's primitive fields (not the object
    // identity, which changes every render) plus the rendered viewport.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightRect?.left, highlightRect?.top, highlightRect?.width, highlightRect?.height, viewportSize]);

  const effectiveTotal = pageCount || total;
  const goPrev = () => onPageChange(Math.max(1, page - 1));
  const goNext = () => onPageChange(Math.min(effectiveTotal || page, page + 1));
  const zoomIn = () => setZoom((z) => Math.min(MAX_ZOOM, +(z + ZOOM_STEP).toFixed(2)));
  const zoomOut = () => setZoom((z) => Math.max(MIN_ZOOM, +(z - ZOOM_STEP).toFixed(2)));
  const resetZoom = () => setZoom(1);

  return (
    <div className="flex h-full min-h-0 flex-col bg-neutral-100">
      <div className="flex items-center justify-between gap-2 border-b border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={goPrev}
            disabled={page <= 1}
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50 disabled:opacity-30"
            aria-label="Previous page"
          >
            ‹
          </button>
          <input
            type="number"
            min={1}
            max={effectiveTotal || undefined}
            value={page}
            onChange={(e) => {
              const next = Number(e.target.value);
              if (Number.isFinite(next) && next >= 1 && next <= (effectiveTotal || next)) {
                onPageChange(next);
              }
            }}
            className="w-12 rounded border border-neutral-300 px-1 py-1 text-center text-xs tabular-nums"
            aria-label="Page number"
          />
          <span className="text-xs tabular-nums text-neutral-500">/ {effectiveTotal || "?"}</span>
          <button
            type="button"
            onClick={goNext}
            disabled={effectiveTotal > 0 && page >= effectiveTotal}
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50 disabled:opacity-30"
            aria-label="Next page"
          >
            ›
          </button>
        </div>
        <div className="min-w-0 flex-1 truncate text-center text-xs text-neutral-500" title={title}>
          {title}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={zoomOut}
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50"
            aria-label="Zoom out"
          >
            −
          </button>
          <button
            type="button"
            onClick={resetZoom}
            className="rounded border border-neutral-300 px-2 py-1 text-xs tabular-nums hover:bg-neutral-50"
            aria-label="Reset zoom"
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            type="button"
            onClick={zoomIn}
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50"
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
      </div>
      <div ref={scrollRef} className="relative flex-1 overflow-auto p-4">
        {loadError ? (
          <div className="p-6 text-sm text-red-600">Could not load PDF: {loadError}</div>
        ) : (
          <div className="relative mx-auto w-fit shadow-lg">
            <canvas ref={canvasRef} className="block" />
            {/* PDF.js text layer: selectable, absolutely positioned over the
                canvas. `.textLayer` styling comes from pdf_viewer.css. */}
            <div
              ref={textLayerRef}
              className="textLayer"
              style={{ position: "absolute", inset: 0 }}
            />
            {/* Deep-zoom region highlight (geometric; exact-text is #145). */}
            {highlightRect && viewportSize ? (
              <svg
                className="pointer-events-none absolute left-0 top-0"
                width={viewportSize.w}
                height={viewportSize.h}
                style={{ width: viewportSize.w, height: viewportSize.h }}
              >
                <rect
                  data-testid="pdf-highlight"
                  x={highlightRect.left}
                  y={highlightRect.top}
                  width={highlightRect.width}
                  height={highlightRect.height}
                  fill="rgba(14, 165, 233, 0.18)"
                  stroke="#0369A1"
                  strokeWidth={2}
                />
              </svg>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
