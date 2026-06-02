export type Rect = { x: number; y: number; w: number; h: number };

/**
 * Convert a gold-region bbox to an image-space rectangle.
 *
 * Gold bboxes use Docling's BOTTOM-LEFT (PDF user-space) origin, but the
 * element ORDER within the 4-tuple is not guaranteed: the vision-LLM region
 * extractor emits `[left, top, right, bottom]` for some documents and
 * `[left, bottom, right, top]` for others. The previous code assumed a fixed
 * order (`height = bbox[1] - bbox[3]`), so for the other ordering every region
 * collapsed to a negative height and rendered invisibly.
 *
 * Taking min/max per axis makes the mapping order-independent: the box spans
 * `[min..max]` horizontally and `[min..max]` in PDF-y, and bottom-left origin
 * maps the larger PDF-y to the image's top edge. A region can never collapse.
 */
export function bboxToImageRect(
  bbox: number[] | undefined,
  pageW: number,
  pageH: number,
  imgW: number,
  imgH: number,
): Rect | null {
  if (!bbox || bbox.length < 4) return null;
  const [a, b, c, d] = bbox;
  if (a === undefined || b === undefined || c === undefined || d === undefined) return null;
  if (pageW <= 0 || pageH <= 0) return null;
  const left = Math.min(a, c);
  const right = Math.max(a, c);
  const yLow = Math.min(b, d);
  const yHigh = Math.max(b, d);
  const sx = imgW / pageW;
  const sy = imgH / pageH;
  return {
    x: left * sx,
    y: (pageH - yHigh) * sy,
    w: (right - left) * sx,
    h: (yHigh - yLow) * sy,
  };
}
