/**
 * Selection -> reference `source_ref` mapping for the PDF source viewer (#110b).
 *
 * Pure geometry + shape helpers, kept out of the React component so the
 * selection -> `source_ref` contract is unit-testable without PDF.js or jsdom.
 *
 * Coordinate conventions:
 *   - A text selection yields client rects in CSS pixels (top-left origin),
 *     which we union into a single page-relative pixel rect via
 *     `unionRectsRelativeTo`.
 *   - `viewportRectToBbox` inverts `bboxToViewportRect` (lib/pdfHighlight): it
 *     maps that rendered pixel rect back to PDF user-space points (bottom-left
 *     origin) so the stored `bbox` matches the convention every other locator
 *     uses (spec rows, gold regions, deep-zoom highlight).
 */
import type { PixelRect } from "@/lib/pdfHighlight";
import type { Region } from "@/api/documents";
import type { SourceRef } from "@/stores/canvasStore";

/**
 * Union a set of client rects into one rect in the coordinate space of
 * `origin` (a reference rect, typically the text layer's bounding box).
 * Returns null when there are no usable rects (collapsed selection).
 */
export function unionRectsRelativeTo(
  rects: Array<{ left: number; top: number; right: number; bottom: number }>,
  origin: { left: number; top: number },
): PixelRect | null {
  const usable = rects.filter((r) => r.right > r.left && r.bottom > r.top);
  if (usable.length === 0) return null;
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  for (const r of usable) {
    left = Math.min(left, r.left);
    top = Math.min(top, r.top);
    right = Math.max(right, r.right);
    bottom = Math.max(bottom, r.bottom);
  }
  return {
    left: left - origin.left,
    top: top - origin.top,
    width: right - left,
    height: bottom - top,
  };
}

/**
 * Invert `bboxToViewportRect`: map a rendered-pixel rect (top-left origin, CSS
 * px) back to a PDF user-space bbox in points (bottom-left origin), returned as
 * `[x0, y0, x1, y1]` with `y0 < y1`. `pageW`/`pageH` are the page size in
 * points; `viewportW`/`viewportH` are the rendered size in CSS px (page size *
 * scale). Returns null when any dimension is unusable.
 */
export function viewportRectToBbox(
  rect: PixelRect,
  pageW: number,
  pageH: number,
  viewportW: number,
  viewportH: number,
): number[] | null {
  if (pageW <= 0 || pageH <= 0 || viewportW <= 0 || viewportH <= 0) return null;
  if (rect.width <= 0 || rect.height <= 0) return null;
  const sx = pageW / viewportW;
  const sy = pageH / viewportH;
  const x0 = rect.left * sx;
  const x1 = (rect.left + rect.width) * sx;
  // Top-left pixel origin -> bottom-left PDF origin: the smaller pixel-y (top)
  // maps to the larger PDF-y.
  const yTop = pageH - rect.top * sy;
  const yBottom = pageH - (rect.top + rect.height) * sy;
  return [x0, Math.min(yBottom, yTop), x1, Math.max(yBottom, yTop)];
}

/** Normalise a 4-tuple bbox to `[xMin, yMin, xMax, yMax]` (order-independent). */
function normaliseBbox(bbox: number[]): [number, number, number, number] | null {
  if (bbox.length < 4) return null;
  const [a, b, c, d] = bbox as [number, number, number, number];
  return [Math.min(a, c), Math.min(b, d), Math.max(a, c), Math.max(b, d)];
}

/** True when two PDF-point bboxes overlap (any shared area). */
export function bboxesOverlap(a: number[], b: number[]): boolean {
  const na = normaliseBbox(a);
  const nb = normaliseBbox(b);
  if (!na || !nb) return false;
  return na[0] < nb[2] && na[2] > nb[0] && na[1] < nb[3] && na[3] > nb[1];
}

/** Fractional overlap area of `a` covered relative to the smaller box. */
function overlapScore(a: number[], b: number[]): number {
  const na = normaliseBbox(a);
  const nb = normaliseBbox(b);
  if (!na || !nb) return 0;
  const ix = Math.max(0, Math.min(na[2], nb[2]) - Math.max(na[0], nb[0]));
  const iy = Math.max(0, Math.min(na[3], nb[3]) - Math.max(na[1], nb[1]));
  return ix * iy;
}

/**
 * Find the gold region on `page` that best overlaps `bbox`, or null. Used to
 * stamp `region_id` on a text selection that falls inside a known region.
 * Picks the region with the largest intersection area (ties -> first).
 */
export function findOverlappingRegion(
  bbox: number[],
  regions: Region[],
  page: number,
): Region | null {
  let best: Region | null = null;
  let bestScore = 0;
  for (const region of regions) {
    if (region.page !== undefined && region.page !== page) continue;
    if (!region.id || !region.bbox) continue;
    if (!bboxesOverlap(bbox, region.bbox)) continue;
    const score = overlapScore(bbox, region.bbox);
    if (score > bestScore) {
      best = region;
      bestScore = score;
    }
  }
  return best;
}

/**
 * Build the `source_ref` for a text selection: the exact `quote`, `page`, and
 * geometric `bbox`. If the selection overlaps a gold region, stamp its
 * `region_id` too. Returns null when there is nothing to capture.
 */
export function buildTextSourceRef(input: {
  slug: string;
  page: number;
  quote: string;
  bbox: number[] | null;
  regions: Region[];
}): SourceRef | null {
  const quote = input.quote.trim();
  if (!quote || !input.bbox) return null;
  const region = findOverlappingRegion(input.bbox, input.regions, input.page);
  const source_ref: SourceRef = {
    slug: input.slug,
    page: input.page,
    bbox: input.bbox,
    detail: { quote },
  };
  if (region?.id) source_ref.region_id = region.id;
  return source_ref;
}

/**
 * Build the `source_ref` for a region / table / image selection: the region's
 * `bbox` + `region_id`. Returns null when the region lacks a bbox.
 */
export function buildRegionSourceRef(input: {
  slug: string;
  page: number;
  region: Region;
}): SourceRef | null {
  const { region } = input;
  if (!region.bbox) return null;
  const source_ref: SourceRef = {
    slug: input.slug,
    page: input.page,
    bbox: region.bbox,
  };
  if (region.id) source_ref.region_id = region.id;
  return source_ref;
}

/** A concise default label for a captured reference (server allows null). */
export function defaultReferenceLabel(input: {
  quote?: string;
  region?: Region;
  page: number;
}): string {
  if (input.quote) {
    const trimmed = input.quote.trim().replace(/\s+/g, " ");
    const snippet = trimmed.length > 60 ? `${trimmed.slice(0, 57)}...` : trimmed;
    return `"${snippet}"`;
  }
  if (input.region) {
    const kind = input.region.kind ?? "region";
    const title = input.region.title ? `: ${input.region.title}` : "";
    return `${kind}${title} (p.${input.page})`;
  }
  return `Reference (p.${input.page})`;
}
