import type { PixelRect } from "@/lib/pdfHighlight";

export const MAGNIFIER_SCALE = 2.5;
const WIDTH = 220;
const HEIGHT = 112;
const GAP = 12;
const MIN_WIDTH = 80;
const MIN_HEIGHT = 56;

export function intersectRects(a: PixelRect, b: PixelRect): PixelRect {
  const left = Math.max(a.left, b.left);
  const top = Math.max(a.top, b.top);
  return {
    left, top,
    width: Math.max(0, Math.min(a.left + a.width, b.left + b.width) - left),
    height: Math.max(0, Math.min(a.top + a.height, b.top + b.height) - top),
  };
}

/** Fit beside the source, flipping at the page/viewport edge, never over it. */
export function placeMagnifier(source: PixelRect, bounds: PixelRect): PixelRect | null {
  if (![source.left, source.top, source.width, source.height,
    bounds.left, bounds.top, bounds.width, bounds.height].every(Number.isFinite)
    || source.width <= 0 || source.height <= 0) return null;
  const right = bounds.left + bounds.width;
  const bottom = bounds.top + bounds.height;
  const spaces: PixelRect[] = [
    { left: Math.max(bounds.left, source.left + source.width + GAP), top: bounds.top,
      width: right - Math.max(bounds.left, source.left + source.width + GAP), height: bounds.height },
    { left: bounds.left, top: bounds.top,
      width: Math.min(right, source.left - GAP) - bounds.left, height: bounds.height },
    { left: bounds.left, top: Math.max(bounds.top, source.top + source.height + GAP),
      width: bounds.width, height: bottom - Math.max(bounds.top, source.top + source.height + GAP) },
    { left: bounds.left, top: bounds.top,
      width: bounds.width, height: Math.min(bottom, source.top - GAP) - bounds.top },
  ];
  for (const [side, space] of spaces.entries()) {
    const width = Math.floor(Math.min(WIDTH, space.width));
    const height = Math.floor(Math.min(HEIGHT, space.height));
    if (width < MIN_WIDTH || height < MIN_HEIGHT) continue;
    const desiredLeft = side === 0 ? space.left
      : side === 1 ? space.left + space.width - width
      : source.left + source.width / 2 - width / 2;
    const desiredTop = side === 2 ? space.top
      : side === 3 ? space.top + space.height - height
      : source.top + source.height / 2 - height / 2;
    return {
      left: Math.max(space.left, Math.min(desiredLeft, space.left + space.width - width)),
      top: Math.max(space.top, Math.min(desiredTop, space.top + space.height - height)),
      width, height,
    };
  }
  return null;
}
