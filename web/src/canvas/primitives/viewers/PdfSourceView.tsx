import { useCallback, useEffect, useRef, useState } from "react";

import "pdfjs-dist/web/pdf_viewer.css";

import { documents, type Region } from "@/api/documents";
import { references } from "@/api/references";
import { bboxToViewportRect, scrollOffsetForRect } from "@/lib/pdfHighlight";
import type { SourceRef } from "@/stores/canvasStore";

import {
  buildRegionSourceRef,
  buildTextSourceRef,
  defaultReferenceLabel,
  unionRectsRelativeTo,
  viewportRectToBbox,
} from "./makeReference";
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
 *
 * #110b adds the human authoring surface: a text selection (or a click on a
 * gold region) raises a "Make reference" action that captures the exact quote
 * + page + geometric bbox (+ region_id when it overlaps a region) and writes a
 * canvas-scoped reference through the existing references store op.
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
  /**
   * The canvas this viewer authors references into. References are
   * canvas-scoped (#147); without a canvas slug the "Make reference" action is
   * hidden (e.g. a standalone document preview with no canvas context).
   */
  canvasSlug?: string;
};

// A pending "Make reference" action: the captured source_ref plus where to
// float the action button (page-pixel space) and a label for the toast.
type PendingAction = {
  sourceRef: SourceRef;
  label: string;
  anchor: { left: number; top: number };
  rect: { left: number; top: number; width: number; height: number };
};

export function PdfSourceView({
  slug,
  page,
  total,
  highlightBbox,
  highlightPage,
  title,
  onPageChange,
  canvasSlug,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const textLayerRef = useRef<HTMLDivElement | null>(null);
  const pageRef = useRef<HTMLDivElement | null>(null);
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
  // Gold regions on the current page: drive region selection + overlap->region_id.
  const [regions, setRegions] = useState<Region[]>([]);
  // The captured-but-not-yet-saved selection (text or region).
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [saving, setSaving] = useState(false);
  // Lightweight confirmation: toast text + the bbox to flash (PDF points).
  const [toast, setToast] = useState<string | null>(null);
  const [confirmBbox, setConfirmBbox] = useState<number[] | null>(null);

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

  // Gold regions for the current page (best-effort; empty on failure). Used to
  // stamp region_id on a text selection and to offer region-level capture.
  useEffect(() => {
    let cancel = false;
    setRegions([]);
    documents.regions(slug, page)
      .then((rs) => { if (!cancel) setRegions(rs); })
      .catch(() => { if (!cancel) setRegions([]); });
    return () => { cancel = true; };
  }, [slug, page]);

  // Clear a pending capture / confirmation when the page or document changes.
  useEffect(() => {
    setPending(null);
    setConfirmBbox(null);
  }, [slug, page]);

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

  // Map a captured PDF-points bbox into the current rendered pixel space so the
  // confirmation flash + the pending-selection outline can be drawn.
  const bboxToRect = useCallback(
    (bbox: number[] | null | undefined) =>
      bbox && pageSize && viewportSize
        ? bboxToViewportRect(bbox, pageSize.w, pageSize.h, {
            width: viewportSize.w,
            height: viewportSize.h,
          })
        : null,
    [pageSize, viewportSize],
  );

  // Text selection -> pending "Make reference" action. Runs on mouseup inside
  // the page so we read the final selection geometry once it settles.
  const onPageMouseUp = useCallback(() => {
    if (!canvasSlug) return;
    const pageEl = pageRef.current;
    const textLayerDiv = textLayerRef.current;
    if (!pageEl || !textLayerDiv || !pageSize || !viewportSize) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
    const quote = sel.toString();
    if (!quote.trim()) return;
    const range = sel.getRangeAt(0);
    // Selection must live inside this page's text layer.
    if (!textLayerDiv.contains(range.commonAncestorContainer)) return;

    const origin = pageEl.getBoundingClientRect();
    const clientRects = Array.from(range.getClientRects());
    const rect = unionRectsRelativeTo(clientRects, origin);
    if (!rect) return;
    const bbox = viewportRectToBbox(rect, pageSize.w, pageSize.h, viewportSize.w, viewportSize.h);
    const sourceRef = buildTextSourceRef({ slug, page, quote, bbox, regions });
    if (!sourceRef) return;
    setConfirmBbox(null);
    setPending({
      sourceRef,
      label: defaultReferenceLabel({ quote, page }),
      anchor: { left: rect.left + rect.width / 2, top: rect.top },
      rect,
    });
  }, [canvasSlug, pageSize, viewportSize, slug, page, regions]);

  // Region / table / image -> pending action: capture the region bbox + id.
  const captureRegion = useCallback(
    (region: Region) => {
      if (!canvasSlug) return;
      const sourceRef = buildRegionSourceRef({ slug, page, region });
      if (!sourceRef) return;
      const rect = bboxToRect(region.bbox);
      if (!rect) return;
      window.getSelection()?.removeAllRanges();
      setConfirmBbox(null);
      setPending({
        sourceRef,
        label: defaultReferenceLabel({ region, page }),
        anchor: { left: rect.left + rect.width / 2, top: rect.top },
        rect,
      });
    },
    [canvasSlug, slug, page, bboxToRect],
  );

  const cancelPending = useCallback(() => {
    setPending(null);
    window.getSelection()?.removeAllRanges();
  }, []);

  const confirmReference = useCallback(async () => {
    if (!canvasSlug || !pending || saving) return;
    setSaving(true);
    try {
      await references.create(canvasSlug, {
        source_ref: pending.sourceRef,
        label: pending.label,
        created_by: "human",
      });
      // Confirmation: flash the captured bbox + a toast for a beat.
      setConfirmBbox(pending.sourceRef.bbox ?? null);
      setToast("Reference created");
      setPending(null);
      window.getSelection()?.removeAllRanges();
    } catch (err) {
      setToast(err instanceof Error ? `Could not create reference: ${err.message}` : "Could not create reference");
    } finally {
      setSaving(false);
    }
  }, [canvasSlug, pending, saving]);

  // Auto-dismiss the toast + the confirmation flash.
  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => {
      setToast(null);
      setConfirmBbox(null);
    }, 2200);
    return () => window.clearTimeout(id);
  }, [toast]);

  const effectiveTotal = pageCount || total;
  const goPrev = () => onPageChange(Math.max(1, page - 1));
  const goNext = () => onPageChange(Math.min(effectiveTotal || page, page + 1));
  const zoomIn = () => setZoom((z) => Math.min(MAX_ZOOM, +(z + ZOOM_STEP).toFixed(2)));
  const zoomOut = () => setZoom((z) => Math.max(MIN_ZOOM, +(z - ZOOM_STEP).toFixed(2)));
  const resetZoom = () => setZoom(1);

  const confirmRect = bboxToRect(confirmBbox);

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
          <div ref={pageRef} className="relative mx-auto w-fit shadow-lg" onMouseUp={onPageMouseUp}>
            <canvas ref={canvasRef} className="block" />
            {/* PDF.js text layer: selectable, absolutely positioned over the
                canvas. `.textLayer` styling comes from pdf_viewer.css. */}
            <div
              ref={textLayerRef}
              className="textLayer"
              style={{ position: "absolute", inset: 0 }}
            />
            {/* Region capture overlay (#110b): gold-region outlines that
                promote to a reference on click. Only the dashed OUTLINE is
                interactive (`pointer-events: stroke`) so the region interior
                stays free for text selection underneath. Only mounted when a
                canvas is available to author into. */}
            {canvasSlug && viewportSize ? (
              <svg
                data-testid="region-capture-layer"
                className="absolute left-0 top-0"
                width={viewportSize.w}
                height={viewportSize.h}
                style={{ width: viewportSize.w, height: viewportSize.h, pointerEvents: "none" }}
              >
                {regions.map((region, idx) => {
                  const rect = bboxToRect(region.bbox);
                  if (!rect) return null;
                  const rid = region.id ?? `r${idx}`;
                  return (
                    <rect
                      key={rid}
                      data-testid="region-capture-rect"
                      data-region-id={region.id ?? ""}
                      x={rect.left}
                      y={rect.top}
                      width={rect.width}
                      height={rect.height}
                      fill="none"
                      stroke="rgba(14, 165, 233, 0.35)"
                      strokeWidth={3}
                      strokeDasharray="3 3"
                      pointerEvents="stroke"
                      style={{ cursor: "pointer" }}
                      onClick={(e) => {
                        e.stopPropagation();
                        captureRegion(region);
                      }}
                    >
                      <title>{region.title ?? region.kind ?? rid} — click outline to make reference</title>
                    </rect>
                  );
                })}
              </svg>
            ) : null}
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
            {/* Pending-selection outline (the geometry about to be captured). */}
            {pending && viewportSize ? (
              <svg
                className="pointer-events-none absolute left-0 top-0"
                width={viewportSize.w}
                height={viewportSize.h}
                style={{ width: viewportSize.w, height: viewportSize.h }}
              >
                <rect
                  data-testid="pending-outline"
                  x={pending.rect.left}
                  y={pending.rect.top}
                  width={pending.rect.width}
                  height={pending.rect.height}
                  fill="rgba(99, 102, 241, 0.14)"
                  stroke="#6366F1"
                  strokeWidth={1.5}
                  strokeDasharray="4 2"
                />
              </svg>
            ) : null}
            {/* Confirmation flash: briefly emphasise the captured bbox. */}
            {confirmRect && viewportSize ? (
              <svg
                className="pointer-events-none absolute left-0 top-0"
                width={viewportSize.w}
                height={viewportSize.h}
                style={{ width: viewportSize.w, height: viewportSize.h }}
              >
                <rect
                  data-testid="reference-confirm-flash"
                  x={confirmRect.left}
                  y={confirmRect.top}
                  width={confirmRect.width}
                  height={confirmRect.height}
                  fill="rgba(34, 197, 94, 0.22)"
                  stroke="#16A34A"
                  strokeWidth={2}
                />
              </svg>
            ) : null}
            {/* Floating "Make reference" context action, anchored above the
                selection / region. Pointer events on so it is clickable. */}
            {pending ? (
              <div
                data-testid="make-reference-action"
                className="absolute z-20 flex -translate-x-1/2 -translate-y-full items-center gap-1 rounded-md border border-neutral-300 bg-white p-1 shadow-lg"
                style={{ left: pending.anchor.left, top: Math.max(pending.anchor.top - 6, 0) }}
                onMouseDown={(e) => e.preventDefault()}
              >
                <button
                  type="button"
                  onClick={confirmReference}
                  disabled={saving}
                  className="rounded bg-sky-600 px-2 py-1 text-xs font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Make reference"}
                </button>
                <button
                  type="button"
                  onClick={cancelPending}
                  className="rounded px-1.5 py-1 text-xs text-neutral-500 hover:bg-neutral-100"
                  aria-label="Cancel reference"
                >
                  ✕
                </button>
              </div>
            ) : null}
          </div>
        )}
        {/* Lightweight confirmation toast. */}
        {toast ? (
          <div
            data-testid="reference-toast"
            role="status"
            className="pointer-events-none absolute bottom-4 left-1/2 z-30 -translate-x-1/2 rounded-md bg-neutral-900/90 px-3 py-1.5 text-xs font-medium text-white shadow-lg"
          >
            {toast}
          </div>
        ) : null}
      </div>
    </div>
  );
}
