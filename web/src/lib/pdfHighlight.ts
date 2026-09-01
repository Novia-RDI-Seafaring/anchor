/**
 * Geometry mapping for the deep-zoom bbox highlight in the real-PDF viewer.
 *
 * PDF.js renders a page through a viewport at a given `scale`. The viewport
 * exposes the page size in PDF points (`viewBox` width/height) and the
 * rendered size in CSS pixels (`width`/`height`). A region bbox arrives in
 * the canonical convention (#281, OIP `pdf-page-bbox`): PDF points, TOP-LEFT
 * origin, `[left, top, right, bottom]`. Element order is still normalised per
 * axis so a legacy or hand-typed box can never collapse.
 *
 * This module scales such a bbox into the rendered pixel space the overlay
 * div lives in (also top-left, CSS px). It mirrors `bboxToImageRect`, but
 * keyed off the PDF.js viewport instead of a rasterised page image, so it
 * stays correct at any zoom level.
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
 * Map a region bbox (PDF points, top-left origin, order-normalised) to a
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
    // Top-left PDF origin (#281): the smaller PDF-y is the top edge.
    top: yLow * sy,
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
