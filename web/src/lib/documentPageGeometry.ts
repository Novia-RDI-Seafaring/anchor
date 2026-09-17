/** Source-page dimensions in PDF points, independent of raster resolution. */
export type DocumentPageGeometry = { width: number; height: number };

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function dimension(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/**
 * Parse gold-map.pages_meta at the API seam. Current silver declares
 * pages[page].page_size in source points. The older flat page -> width/height
 * consumer contract remains explicit compatibility. Malformed current data
 * never falls through to legacy fields or inferred DPI.
 *
 * Absence from the result means unknown geometry. Raster dimensions, when
 * needed, come separately from the loaded image's naturalWidth/naturalHeight;
 * they cannot establish source-page dimensions.
 */
export function parseDocumentPageGeometry(raw: unknown): Record<number, DocumentPageGeometry> {
  const meta = object(raw);
  if (!meta || (meta.bbox_origin !== undefined && meta.bbox_origin !== "top-left")) return {};
  const current = Object.hasOwn(meta, "pages");
  const entries = current ? object(meta.pages) : meta;
  if (!entries) return {};
  const result: Record<number, DocumentPageGeometry> = {};
  for (const [key, value] of Object.entries(entries)) {
    if (!/^[1-9]\d*$/.test(key) || !Number.isSafeInteger(Number(key))) continue;
    const entry = object(value);
    if (!entry) continue;
    const size = current ? entry.page_size : [entry.width, entry.height];
    if (!Array.isArray(size) || size.length !== 2) continue;
    const [width, height] = size;
    if (dimension(width) && dimension(height)) result[Number(key)] = { width, height };
  }
  return result;
}
