/**
 * Geometry for the Preview-style continuous PDF viewer (#220 part A).
 *
 * The viewer stacks every page top-to-bottom in ONE scroller at the current
 * zoom. To keep this smooth on large PDFs we virtualize: only the pages near
 * the viewport mount a real PDF.js canvas + text layer, the rest are sized
 * placeholders so the total scroll height and every scroll-to-page calculation
 * stay correct.
 *
 * This module holds the pure math behind that layout (cumulative page offsets,
 * page-in-view detection, scroll targets, deep-zoom highlight targeting) so it
 * is unit-testable without PDF.js or jsdom. Pixel sizes here are in CSS px at
 * the current zoom unless noted otherwise.
 */

export type PageLayoutItem = {
  /** 1-based page number. */
  page: number;
  /** Rendered width of the page in CSS px at the current zoom. */
  width: number;
  /** Rendered height of the page in CSS px at the current zoom. */
  height: number;
  /** Distance from the top of the scroll content to this page's top edge. */
  top: number;
};

/** Vertical gap (CSS px) drawn between stacked pages. */
export const PAGE_GAP = 16;

/**
 * Build the stacked layout: for each page (in order) its top offset and height
 * in CSS px at the current zoom, including the inter-page gap. `pageSizes` is a
 * map of 1-based page number -> {w,h} in PDF points (unscaled). Pages without a
 * known size fall back to `fallback` (the natural size of the first known page,
 * or a Letter-ish default) so placeholders are roughly right before their real
 * size is measured.
 */
export function buildPageLayout(
  pageCount: number,
  pageSizes: Record<number, { w: number; h: number }>,
  zoom: number,
  fallback: { w: number; h: number },
): { items: PageLayoutItem[]; totalHeight: number } {
  const items: PageLayoutItem[] = [];
  let top = 0;
  for (let page = 1; page <= pageCount; page++) {
    const size = pageSizes[page] ?? fallback;
    const width = Math.max(1, size.w * zoom);
    const height = Math.max(1, size.h * zoom);
    items.push({ page, width, height, top });
    top += height + PAGE_GAP;
  }
  // Trailing gap is not part of the content height.
  const totalHeight = top > 0 ? top - PAGE_GAP : 0;
  return { items, totalHeight };
}

/**
 * The scroll-top that brings page `page`'s top edge to the top of the viewport
 * (minus a small `margin` so it does not butt against the chrome). Clamped to
 * [0, maxScroll].
 */
export function scrollTopForPage(
  items: PageLayoutItem[],
  page: number,
  containerH: number,
  contentH: number,
  margin = PAGE_GAP,
): number {
  const item = items.find((it) => it.page === page);
  if (!item) return 0;
  const maxTop = Math.max(0, contentH - containerH);
  return Math.min(Math.max(0, item.top - margin), maxTop);
}

/**
 * The page whose area dominates the viewport at scroll position `scrollTop`.
 * Used to keep the "current page" pointer (toolbar input, thumbnail highlight,
 * uiStore page) in sync as the user scrolls the continuous view. Picks the page
 * with the largest visible height; ties resolve to the lower page number.
 */
export function pageInView(
  items: PageLayoutItem[],
  scrollTop: number,
  containerH: number,
): number {
  if (items.length === 0) return 1;
  const viewTop = scrollTop;
  const viewBottom = scrollTop + containerH;
  let best = items[0]!.page;
  let bestVisible = -1;
  for (const it of items) {
    const top = it.top;
    const bottom = it.top + it.height;
    const visible = Math.max(0, Math.min(bottom, viewBottom) - Math.max(top, viewTop));
    if (visible > bestVisible) {
      bestVisible = visible;
      best = it.page;
    }
  }
  return best;
}

/**
 * The window of pages to actually render (mount a canvas + text layer for):
 * the pages overlapping the viewport plus `overscan` neighbours on each side.
 * Everything else stays a sized placeholder. Returns an inclusive [start, end]
 * 1-based page range.
 */
export function visiblePageRange(
  items: PageLayoutItem[],
  scrollTop: number,
  containerH: number,
  overscan = 1,
): { start: number; end: number } {
  if (items.length === 0) return { start: 1, end: 1 };
  const viewTop = scrollTop;
  const viewBottom = scrollTop + containerH;
  let first = items.length; // index
  let last = -1;
  for (let i = 0; i < items.length; i++) {
    const it = items[i]!;
    const top = it.top;
    const bottom = it.top + it.height;
    if (bottom >= viewTop && top <= viewBottom) {
      if (i < first) first = i;
      if (i > last) last = i;
    }
  }
  if (last < 0) {
    // Nothing overlaps (e.g. measured mid-load) — fall back to the first page.
    first = 0;
    last = 0;
  }
  const startIdx = Math.max(0, first - overscan);
  const endIdx = Math.min(items.length - 1, last + overscan);
  return { start: items[startIdx]!.page, end: items[endIdx]!.page };
}

/**
 * The scroll-top that brings a within-page rect (CSS px relative to the page's
 * own top-left, at the current zoom) into view, vertically centred, in the
 * continuous scroller. Combines the page's stacked top offset with the rect's
 * offset inside the page. Clamped to [0, maxScroll].
 */
export function scrollTopForPageRect(
  items: PageLayoutItem[],
  page: number,
  rectTop: number,
  rectHeight: number,
  containerH: number,
  contentH: number,
): number {
  const item = items.find((it) => it.page === page);
  if (!item) return 0;
  const absoluteCentre = item.top + rectTop + rectHeight / 2;
  const target = absoluteCentre - containerH / 2;
  const maxTop = Math.max(0, contentH - containerH);
  return Math.min(Math.max(0, target), maxTop);
}

/**
 * Zoom after one wheel event with Cmd/Ctrl held, or one trackpad pinch step
 * (browsers deliver pinch as a wheel event with `ctrlKey` set). Exponential so
 * zooming in then out by the same amount returns to the start, and continuous
 * so a trackpad feels smooth. Wheel up (negative deltaY) zooms in.
 *
 * Scaling follows the common d3-zoom convention: line-mode deltas (Firefox
 * mouse wheels) are ~20x pixel deltas, page mode is one page per unit, and
 * pinch deltas are small, so they are boosted 10x. One mouse-wheel notch
 * (deltaY 100 px) changes zoom by about 15%.
 */
export function wheelZoom(
  zoom: number,
  deltaY: number,
  deltaMode: number,
  pinch: boolean,
  min: number,
  max: number,
): number {
  const unit = deltaMode === 1 ? 0.05 : deltaMode === 2 ? 1 : 0.002;
  const next = zoom * Math.pow(2, -deltaY * unit * (pinch ? 10 : 1));
  return Math.min(max, Math.max(min, +next.toFixed(3)));
}

/**
 * A zoom-invariant point in the stacked document: which page, and where on it
 * as a fraction of the page's size. `fx` is relative to the content width.
 */
export type ZoomAnchor = { page: number; fy: number; fx: number };

/**
 * The anchor under a content-space point (CSS px from the top-left of the
 * stacked content). Points in the gap below a page belong to that page with
 * `fy > 1`, so the math stays continuous between pages.
 */
export function anchorAt(
  items: PageLayoutItem[],
  contentWidth: number,
  x: number,
  y: number,
): ZoomAnchor | null {
  if (items.length === 0) return null;
  let item = items[0]!;
  for (const it of items) {
    if (it.top <= y) item = it;
    else break;
  }
  return {
    page: item.page,
    fy: (y - item.top) / item.height,
    fx: contentWidth > 0 ? x / contentWidth : 0,
  };
}

/**
 * The content-space point for an anchor in a (re-zoomed) layout. The viewer
 * subtracts the pointer's offset inside the scroller to get the scroll
 * position that keeps the anchored spot under the pointer.
 */
export function pointForAnchor(
  items: PageLayoutItem[],
  contentWidth: number,
  anchor: ZoomAnchor,
): { x: number; y: number } | null {
  const item = items.find((it) => it.page === anchor.page);
  if (!item) return null;
  return { x: anchor.fx * contentWidth, y: item.top + anchor.fy * item.height };
}
