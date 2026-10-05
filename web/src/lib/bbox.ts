export type Rect = { x: number; y: number; w: number; h: number };

function normalizedBbox(bbox: number[] | undefined): [number, number, number, number] | null {
  if (!bbox || bbox.length < 4) return null;
  const [a, b, c, d] = bbox;
  if (a === undefined || b === undefined || c === undefined || d === undefined) return null;
  return [
    Math.min(a, c),
    Math.min(b, d),
    Math.max(a, c),
    Math.max(b, d),
  ];
}

export function sameBbox(a: number[] | undefined, b: number[] | undefined): boolean {
  const left = normalizedBbox(a);
  const right = normalizedBbox(b);
  if (!left || !right) return false;
  return left.every((value, index) => Math.abs(value - right[index]!) <= 0.5);
}

/**
 * Convert a gold-region bbox to an image-space rectangle.
 *
 * Gold bboxes use the canonical top-left PDF-points convention (#281), the
 * same orientation as the rendered image, so this is a pure scale. Element
 * order within the 4-tuple is still normalised per axis (min/max), so a
 * legacy or hand-typed `[left, bottom, right, top]` box can never collapse to
 * a negative height and render invisibly.
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
    y: yLow * sy,
    w: (right - left) * sx,
    h: (yHigh - yLow) * sy,
  };
}
