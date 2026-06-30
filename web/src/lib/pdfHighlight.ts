/**
 * Geometry mapping for the deep-zoom bbox highlight in the real-PDF viewer.
 *
 * PDF.js renders a page through a viewport at a given `scale`. The viewport
 * exposes the page size in PDF points (`viewBox` width/height) and the
 * rendered size in CSS pixels (`width`/`height`). A region bbox arrives in
 * Docling's PDF user-space (BOTTOM-LEFT origin) and the element order inside
 * the 4-tuple is NOT guaranteed (`[left, top, right, bottom]` for some
 * documents, `[left, bottom, right, top]` for others — see lib/bbox).
 *
 * This module maps such a bbox into the rendered pixel space the overlay div
 * lives in (TOP-LEFT origin, CSS px), order-independently. It mirrors the
 * convention in `bboxToImageRect`, but keyed off the PDF.js viewport instead
 * of a rasterised page image, so it stays correct at any zoom level.
 */

export type PixelRect = { left: number; top: number; width: number; height: number };

/**
 * The slice of a PDF.js `PageViewport` we depend on. Declared locally so the
 * mapping is testable without constructing a real viewport (and so unit tests
 * carry no pdfjs-dist dependency).
 */
export type ViewportLike = {
  /** Rendered width in CSS pixels (page width in points * scale). */
  width: number;
  /** Rendered height in CSS pixels (page height in points * scale). */
  height: number;
};

/**
 * Map a region bbox (PDF points, bottom-left origin, unknown tuple order) to a
 * rectangle in the rendered page's CSS-pixel space (top-left origin).
 *
 * @param bbox    region bbox, length >= 4, in PDF user-space points
 * @param pageW   page width in PDF points (viewBox width, unscaled)
 * @param pageH   page height in PDF points (viewBox height, unscaled)
 * @param viewport rendered viewport (CSS pixel dimensions)
 * @returns the pixel-space rect, or null when the inputs are unusable
 */
export function bboxToViewportRect(
  bbox: number[] | undefined,
  pageW: number,
  pageH: number,
  viewport: ViewportLike,
): PixelRect | null {
  if (!bbox || bbox.length < 4) return null;
  const [a, b, c, d] = bbox;
  if (a === undefined || b === undefined || c === undefined || d === undefined) return null;
  if (pageW <= 0 || pageH <= 0) return null;
  if (viewport.width <= 0 || viewport.height <= 0) return null;

  const left = Math.min(a, c);
  const right = Math.max(a, c);
  const yLow = Math.min(b, d);
  const yHigh = Math.max(b, d);

  const sx = viewport.width / pageW;
  const sy = viewport.height / pageH;

  return {
    left: left * sx,
    // Bottom-left PDF origin: the larger PDF-y maps to the top edge.
    top: (pageH - yHigh) * sy,
    width: (right - left) * sx,
    height: (yHigh - yLow) * sy,
  };
}

/**
 * Compute the scroll offset (in the page container's pixel space) that brings
 * `rect` into view, centred in a viewport of size `containerW` x `containerH`.
 * Clamped to [0, max] so we never scroll past the page edges. Returns the
 * top-left scroll position to assign to the scroll container.
 */
export function scrollOffsetForRect(
  rect: PixelRect,
  containerW: number,
  containerH: number,
  contentW: number,
  contentH: number,
): { left: number; top: number } {
  const targetLeft = rect.left + rect.width / 2 - containerW / 2;
  const targetTop = rect.top + rect.height / 2 - containerH / 2;
  const maxLeft = Math.max(0, contentW - containerW);
  const maxTop = Math.max(0, contentH - containerH);
  return {
    left: Math.min(Math.max(0, targetLeft), maxLeft),
    top: Math.min(Math.max(0, targetTop), maxTop),
  };
}
