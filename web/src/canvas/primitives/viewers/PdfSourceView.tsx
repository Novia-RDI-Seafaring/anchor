import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import "pdfjs-dist/web/pdf_viewer.css";

import { documents, type Region } from "@/api/documents";
import { references } from "@/api/references";
import { bboxToViewportRect } from "@/lib/pdfHighlight";
import {
  buildPageLayout,
  pageInView,
  scrollTopForPage,
  scrollTopForPageRect,
  visiblePageRange,
  type PageLayoutItem,
} from "@/lib/pdfContinuous";
import type { SourceRef } from "@/stores/canvasStore";

import {
  buildRegionSourceRef,
  buildTextSourceRef,
  defaultReferenceLabel,
  unionRectsRelativeTo,
  viewportRectToBbox,
} from "./makeReference";
import { PdfPageCanvas } from "./PdfPageCanvas";
import { loadPdf, pageSizes as readPageSizes, type PdfDoc } from "./pdfjs";

/**
 * PdfSourceView — Preview-style continuous PDF viewer (#220 part A).
 *
 * Stacks EVERY page top-to-bottom in one scroller at the current zoom (macOS
 * Preview / Acrobat style), with a toggleable page-thumbnail rail on the left.
 * Clicking a thumbnail smooth-scrolls to that page; the page dominating the
 * viewport is highlighted in the rail and pushed back through `onPageChange`.
 *
 * Performance: the view virtualizes. Page sizes (PDF points) are read up front
 * so the full scroll height is correct, but only the pages near the viewport
 * mount a real PDF.js canvas + text layer; the rest are sized placeholders.
 * Text selection, the #110b "Make reference" action, the gold-region capture
 * outlines, and the deep-zoom bbox highlight all operate per rendered page.
 *
 * This is the shared inner view used by the docked split-screen pane. It owns
 * no global state beyond the uiStore page pointer passed via props.
 */

const MIN_ZOOM = 0.4;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.2;
const OVERSCAN = 1;
const THUMB_WIDTH = 96; // CSS px of the thumbnail image
// Sensible page-size fallback (US Letter, points) before any size is known.
const FALLBACK_PAGE = { w: 612, h: 792 };

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
  page: number;
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
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const docRef = useRef<PdfDoc | null>(null);
  const destroyRef = useRef<(() => Promise<void>) | null>(null);

  const [zoom, setZoom] = useState(1);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState(total);
  // PDF document instance, exposed via state so render re-fires once loaded.
  const [doc, setDoc] = useState<PdfDoc | null>(null);
  // Page sizes in PDF points (unscaled), keyed by 1-based page number.
  const [pdfPageSizes, setPdfPageSizes] = useState<Record<number, { w: number; h: number }>>({});
  // Rendered viewport size per page (CSS px) once a page has drawn — lets the
  // overlays map a bbox into pixels precisely on rendered pages.
  const [rendered, setRendered] = useState<Record<number, { w: number; h: number }>>({});
  // Scroller geometry, driving virtualization + page-in-view detection.
  const [scrollTop, setScrollTop] = useState(0);
  const [containerSize, setContainerSize] = useState({ w: 0, h: 0 });
  // Gold regions per page (best-effort), used for region capture + region_id.
  const [regionsByPage, setRegionsByPage] = useState<Record<number, Region[]>>({});
  // Thumbnail rail visibility (default shown).
  const [railOpen, setRailOpen] = useState(true);
  // The captured-but-not-yet-saved selection (text or region).
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [saving, setSaving] = useState(false);
  // Lightweight confirmation: toast text + the page/bbox to flash (PDF points).
  const [toast, setToast] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ page: number; bbox: number[] } | null>(null);
  // Set after a programmatic scroll-to-highlight so we only do it once per target.
  const lastHighlightRef = useRef<string | null>(null);

  // Load (and reload on slug change) the PDF document. One shared instance.
  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    setDoc(null);
    setPdfPageSizes({});
    setRendered({});
    setRegionsByPage({});
    setPending(null);
    setConfirm(null);
    lastHighlightRef.current = null;
    loadPdf(documents.pdfUrl(slug))
      .then(async ({ doc: loaded, destroy }) => {
        if (cancelled) {
          void destroy();
          return;
        }
        docRef.current = loaded;
        destroyRef.current = destroy;
        setPageCount(loaded.numPages);
        const sizes = await readPageSizes(loaded);
        if (cancelled) return;
        setPdfPageSizes(sizes);
        setDoc(loaded);
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

  const effectiveTotal = pageCount || total;

  // Fallback page size: the first known PDF page size, else US Letter.
  const fallbackSize = useMemo(() => {
    const first = Object.values(pdfPageSizes)[0];
    return first ?? FALLBACK_PAGE;
  }, [pdfPageSizes]);

  // The stacked layout (page tops + heights in CSS px at the current zoom).
  const { items, totalHeight } = useMemo(
    () => buildPageLayout(effectiveTotal || 0, pdfPageSizes, zoom, fallbackSize),
    [effectiveTotal, pdfPageSizes, zoom, fallbackSize],
  );

  // Widest page (CSS px) — drives the content width so horizontal centering +
  // overflow work even though pages are absolutely positioned.
  const contentWidth = useMemo(
    () => items.reduce((max, it) => Math.max(max, it.width), 0),
    [items],
  );

  // Pages to actually mount a canvas for (visible window + overscan).
  const range = useMemo(
    () => visiblePageRange(items, scrollTop, containerSize.h, OVERSCAN),
    [items, scrollTop, containerSize.h],
  );

  // A page renders its canvas when it is in the virtualization window OR it is
  // the deep-zoom highlight target (so the bbox can be drawn even before the
  // user scrolls it into view — without mounting the whole contiguous span).
  const shouldRenderPage = useCallback(
    (p: number) => (p >= range.start && p <= range.end) || p === highlightPage,
    [range.start, range.end, highlightPage],
  );

  // Track the scroller's size (drives virtualization + fit-width).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => setContainerSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [doc]);

  // Keep the "current page" pointer in sync with the dominant page in view.
  const pageInViewNow = useMemo(
    () => pageInView(items, scrollTop, containerSize.h),
    [items, scrollTop, containerSize.h],
  );
  useEffect(() => {
    if (effectiveTotal > 0 && pageInViewNow !== page) {
      onPageChange(pageInViewNow);
    }
    // Only react to the computed in-view page; `page`/`onPageChange` are stable
    // enough and re-firing on every prop tick would fight user scrolling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageInViewNow, effectiveTotal]);

  // Gold regions for the pages currently in the render window (best-effort).
  useEffect(() => {
    if (!doc) return;
    let cancelled = false;
    for (let p = range.start; p <= range.end; p++) {
      if (regionsByPage[p] !== undefined) continue;
      documents.regions(slug, p)
        .then((rs) => { if (!cancelled) setRegionsByPage((m) => ({ ...m, [p]: rs })); })
        .catch(() => { if (!cancelled) setRegionsByPage((m) => ({ ...m, [p]: [] })); });
    }
    return () => { cancelled = true; };
  }, [doc, slug, range.start, range.end, regionsByPage]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (el) setScrollTop(el.scrollTop);
  }, []);

  // Smooth-scroll to a page (thumbnail click + toolbar jump).
  const scrollToPage = useCallback(
    (target: number) => {
      const el = scrollRef.current;
      if (!el) return;
      const top = scrollTopForPage(items, target, el.clientHeight, totalHeight);
      el.scrollTo({ top, behavior: "smooth" });
    },
    [items, totalHeight],
  );

  // Deep-zoom: when the highlight targets a page, scroll the continuous view to
  // that page's bbox once the geometry needed to place it is known. Runs once
  // per (page,bbox) target.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !highlightPage || !highlightBbox || items.length === 0) return;
    const size = pdfPageSizes[highlightPage];
    if (!size) return;
    const key = `${highlightPage}:${highlightBbox.join(",")}:${zoom}`;
    if (lastHighlightRef.current === key) return;
    const rect = bboxToViewportRect(highlightBbox, size.w, size.h, {
      width: size.w * zoom,
      height: size.h * zoom,
    });
    if (!rect) return;
    const top = scrollTopForPageRect(
      items,
      highlightPage,
      rect.top,
      rect.height,
      el.clientHeight,
      totalHeight,
    );
    el.scrollTo({ top, behavior: "smooth" });
    lastHighlightRef.current = key;
  }, [highlightPage, highlightBbox, items, pdfPageSizes, zoom, totalHeight]);

  // Map a PDF-points bbox to pixel space on a given page using its best-known
  // size (rendered viewport if drawn, else points * zoom).
  const bboxToRectOnPage = useCallback(
    (p: number, bbox: number[] | null | undefined) => {
      if (!bbox) return null;
      const r = rendered[p];
      const size = pdfPageSizes[p];
      if (!size) return null;
      const vw = r?.w ?? size.w * zoom;
      const vh = r?.h ?? size.h * zoom;
      return bboxToViewportRect(bbox, size.w, size.h, { width: vw, height: vh });
    },
    [rendered, pdfPageSizes, zoom],
  );

  const onPageRendered = useCallback((p: number, size: { w: number; h: number }) => {
    setRendered((m) => (m[p]?.w === size.w && m[p]?.h === size.h ? m : { ...m, [p]: size }));
  }, []);

  // Text selection -> pending "Make reference" action on page `p`.
  const onPageMouseUp = useCallback(
    (p: number) => {
      if (!canvasSlug) return;
      const pageEl = pageRefs.current.get(p);
      const size = pdfPageSizes[p];
      const r = rendered[p];
      if (!pageEl || !size || !r) return;
      const textLayerDiv = pageEl.querySelector(".textLayer");
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
      const quote = sel.toString();
      if (!quote.trim()) return;
      const sourceRange = sel.getRangeAt(0);
      if (!textLayerDiv || !textLayerDiv.contains(sourceRange.commonAncestorContainer)) return;

      const origin = pageEl.getBoundingClientRect();
      const clientRects = Array.from(sourceRange.getClientRects());
      const rect = unionRectsRelativeTo(clientRects, origin);
      if (!rect) return;
      const bbox = viewportRectToBbox(rect, size.w, size.h, r.w, r.h);
      const regions = regionsByPage[p] ?? [];
      const sourceRef = buildTextSourceRef({ slug, page: p, quote, bbox, regions });
      if (!sourceRef) return;
      setConfirm(null);
      setPending({
        page: p,
        sourceRef,
        label: defaultReferenceLabel({ quote, page: p }),
        anchor: { left: rect.left + rect.width / 2, top: rect.top },
        rect,
      });
    },
    [canvasSlug, pdfPageSizes, rendered, slug, regionsByPage],
  );

  // Region / table / image -> pending action: capture the region bbox + id.
  const captureRegion = useCallback(
    (p: number, region: Region) => {
      if (!canvasSlug) return;
      const sourceRef = buildRegionSourceRef({ slug, page: p, region });
      if (!sourceRef) return;
      const rect = bboxToRectOnPage(p, region.bbox);
      if (!rect) return;
      window.getSelection()?.removeAllRanges();
      setConfirm(null);
      setPending({
        page: p,
        sourceRef,
        label: defaultReferenceLabel({ region, page: p }),
        anchor: { left: rect.left + rect.width / 2, top: rect.top },
        rect,
      });
    },
    [canvasSlug, slug, bboxToRectOnPage],
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
      if (pending.sourceRef.bbox) {
        setConfirm({ page: pending.page, bbox: pending.sourceRef.bbox });
      }
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
      setConfirm(null);
    }, 2200);
    return () => window.clearTimeout(id);
  }, [toast]);

  const zoomIn = () => setZoom((z) => Math.min(MAX_ZOOM, +(z + ZOOM_STEP).toFixed(2)));
  const zoomOut = () => setZoom((z) => Math.max(MIN_ZOOM, +(z - ZOOM_STEP).toFixed(2)));
  const resetZoom = () => setZoom(1);
  const fitWidth = useCallback(() => {
    const el = scrollRef.current;
    const size = pdfPageSizes[page] ?? fallbackSize;
    if (!el || size.w <= 0) return;
    // Account for the page's horizontal padding (p-4 -> 16px each side).
    const usable = Math.max(1, el.clientWidth - 48);
    setZoom(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, +(usable / size.w).toFixed(3))));
  }, [pdfPageSizes, page, fallbackSize]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-neutral-100">
      <div className="flex items-center justify-between gap-2 border-b border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setRailOpen((v) => !v)}
            aria-pressed={railOpen}
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50"
            title={railOpen ? "Hide thumbnails" : "Show thumbnails"}
            aria-label="Toggle thumbnails"
          >
            ▤
          </button>
          <input
            type="number"
            min={1}
            max={effectiveTotal || undefined}
            value={page}
            onChange={(e) => {
              const next = Number(e.target.value);
              if (Number.isFinite(next) && next >= 1 && next <= (effectiveTotal || next)) {
                scrollToPage(next);
              }
            }}
            className="w-12 rounded border border-neutral-300 px-1 py-1 text-center text-xs tabular-nums"
            aria-label="Page number"
          />
          <span className="text-xs tabular-nums text-neutral-500">/ {effectiveTotal || "?"}</span>
        </div>
        <div className="min-w-0 flex-1 truncate text-center text-xs text-neutral-500" title={title}>
          {title}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={fitWidth}
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50"
            aria-label="Fit width"
            title="Fit width"
          >
            ↔
          </button>
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
      <div className="flex min-h-0 flex-1">
        {/* Thumbnail rail (#220): one thumb per page, click -> scroll-to-page,
            the in-view page is highlighted. Backed by the page-image endpoint
            so it does not contend for the PDF.js worker. */}
        {railOpen && effectiveTotal > 0 ? (
          <div
            data-testid="thumbnail-rail"
            className="w-[120px] shrink-0 overflow-y-auto border-r border-neutral-200 bg-neutral-50 p-2"
          >
            <ul className="flex flex-col gap-2">
              {items.map((it) => {
                const active = it.page === page;
                return (
                  <li key={it.page}>
                    <button
                      type="button"
                      data-testid="thumbnail"
                      data-page={it.page}
                      aria-current={active ? "page" : undefined}
                      onClick={() => scrollToPage(it.page)}
                      className={`block w-full rounded border bg-white p-0.5 text-center ${
                        active ? "border-sky-500 ring-2 ring-sky-300" : "border-neutral-300 hover:border-neutral-400"
                      }`}
                    >
                      <img
                        src={documents.pageImageUrl(slug, it.page)}
                        alt={`Page ${it.page}`}
                        loading="lazy"
                        width={THUMB_WIDTH}
                        className="mx-auto block h-auto w-full"
                      />
                      <span className="block py-0.5 text-[10px] tabular-nums text-neutral-500">{it.page}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="relative flex-1 overflow-auto p-4"
          data-testid="pdf-scroller"
        >
          {loadError ? (
            <div className="p-6 text-sm text-red-600">Could not load PDF: {loadError}</div>
          ) : (
            <div className="relative mx-auto" style={{ height: totalHeight, width: contentWidth || undefined }}>
              {items.map((it) => (
                <PageSlot
                  key={it.page}
                  item={it}
                  doc={doc}
                  zoom={zoom}
                  rendered={rendered[it.page]}
                  shouldRender={shouldRenderPage(it.page)}
                  regions={canvasSlug ? regionsByPage[it.page] ?? [] : []}
                  canvasSlug={canvasSlug}
                  highlightBbox={highlightPage === it.page ? highlightBbox : undefined}
                  confirmBbox={confirm?.page === it.page ? confirm.bbox : undefined}
                  pending={pending?.page === it.page ? pending : null}
                  bboxToRect={(bbox) => bboxToRectOnPage(it.page, bbox)}
                  onMouseUp={() => onPageMouseUp(it.page)}
                  onCaptureRegion={(region) => captureRegion(it.page, region)}
                  onRendered={onPageRendered}
                  onConfirmReference={confirmReference}
                  onCancelPending={cancelPending}
                  saving={saving}
                  registerRef={(el) => {
                    if (el) pageRefs.current.set(it.page, el);
                    else pageRefs.current.delete(it.page);
                  }}
                />
              ))}
            </div>
          )}
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
    </div>
  );
}

type SlotProps = {
  item: PageLayoutItem;
  doc: PdfDoc | null;
  zoom: number;
  rendered?: { w: number; h: number };
  shouldRender: boolean;
  regions: Region[];
  canvasSlug?: string;
  highlightBbox?: number[];
  confirmBbox?: number[];
  pending: PendingAction | null;
  bboxToRect: (bbox: number[] | null | undefined) => { left: number; top: number; width: number; height: number } | null;
  onMouseUp: () => void;
  onCaptureRegion: (region: Region) => void;
  onRendered: (page: number, size: { w: number; h: number }) => void;
  onConfirmReference: () => void;
  onCancelPending: () => void;
  saving: boolean;
  registerRef: (el: HTMLDivElement | null) => void;
};

/**
 * One page in the stack. Mounts a real canvas + text layer + overlays only when
 * `shouldRender`; otherwise it is a sized placeholder so the scroll geometry
 * stays correct. The page box is absolutely positioned at its stacked top.
 */
function PageSlot(props: SlotProps) {
  const {
    item, doc, zoom, rendered, shouldRender, regions, canvasSlug, highlightBbox,
    confirmBbox, pending, bboxToRect, onMouseUp, onCaptureRegion, onRendered,
    onConfirmReference, onCancelPending, saving, registerRef,
  } = props;

  const viewportSize = rendered ?? null;
  const highlightRect = bboxToRect(highlightBbox);
  const confirmRect = bboxToRect(confirmBbox);

  return (
    <div
      ref={registerRef}
      data-testid="pdf-page-slot"
      data-page={item.page}
      className="absolute left-1/2 -translate-x-1/2 bg-white shadow-lg"
      style={{ top: item.top, height: item.height, width: item.width }}
      onMouseUp={onMouseUp}
    >
      {shouldRender && doc ? (
        <PdfPageCanvas doc={doc} page={item.page} zoom={zoom} onRendered={onRendered} />
      ) : null}

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
                  onCaptureRegion(region);
                }}
              >
                <title>{region.title ?? region.kind ?? rid} — click outline to make reference</title>
              </rect>
            );
          })}
        </svg>
      ) : null}

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

      {pending ? (
        <div
          data-testid="make-reference-action"
          className="absolute z-20 flex -translate-x-1/2 -translate-y-full items-center gap-1 rounded-md border border-neutral-300 bg-white p-1 shadow-lg"
          style={{ left: pending.anchor.left, top: Math.max(pending.anchor.top - 6, 0) }}
          onMouseDown={(e) => e.preventDefault()}
        >
          <button
            type="button"
            onClick={onConfirmReference}
            disabled={saving}
            className="rounded bg-sky-600 px-2 py-1 text-xs font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Make reference"}
          </button>
          <button
            type="button"
            onClick={onCancelPending}
            className="rounded px-1.5 py-1 text-xs text-neutral-500 hover:bg-neutral-100"
            aria-label="Cancel reference"
          >
            ✕
          </button>
        </div>
      ) : null}
    </div>
  );
}
