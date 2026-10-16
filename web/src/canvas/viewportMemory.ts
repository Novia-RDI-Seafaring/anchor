/**
 * viewportMemory.ts — where each canvas was last looked at, per browser.
 *
 * A reload used to fit the whole canvas into view, so whoever had zoomed
 * in on one corner to work there lost their place every time. The view is a
 * per-viewer convenience, so it lives in this browser's storage, keyed by
 * canvas, and a canvas never opened here still fits everything.
 */
export type Viewport = { x: number; y: number; zoom: number };

const key = (slug: string) => `anchor.canvas-viewport.${slug}`;

export function loadViewport(slug: string): Viewport | null {
  try {
    const raw = window.localStorage.getItem(key(slug));
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<Viewport>;
    return [v.x, v.y, v.zoom].every((n) => typeof n === "number" && Number.isFinite(n)) && v.zoom! > 0
      ? { x: v.x!, y: v.y!, zoom: v.zoom! }
      : null;
  } catch {
    return null;
  }
}

export function saveViewport(slug: string, viewport: Viewport): void {
  try {
    window.localStorage.setItem(key(slug), JSON.stringify(viewport));
  } catch {
    // Storage blocked or full: the next load fits the canvas, as before.
  }
}
