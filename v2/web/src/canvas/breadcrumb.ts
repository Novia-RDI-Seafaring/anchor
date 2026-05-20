/**
 * Sub-canvas breadcrumb — persists the user's drill-down trail.
 *
 * The trail is the list of slugs visited via a canvas-node double-click,
 * with the current canvas as the last segment. Persisted in
 * `sessionStorage` (key: `anchor:breadcrumb`) so reload keeps the chain,
 * but a fresh tab starts from scratch.
 *
 * Rules:
 *   - `enter(slug)` extends the trail. If `slug` already appears, the
 *     trail is truncated to and including that entry (back-navigation).
 *   - `clear()` resets the trail (used when the user clicks "← All
 *     canvases" or visits a canvas from outside the drill-down flow).
 *   - `reset(slug)` replaces the trail with a single-entry trail —
 *     called when CanvasListPage links into a canvas directly.
 *   - `chain()` returns the current list of slugs.
 *
 * The store does NOT track the parent → child topology server-side. The
 * hierarchy lives in the canvas as `canvas`-typed nodes; the breadcrumb
 * is purely a UI memory of the user's path.
 */

const KEY = "anchor:breadcrumb";

function read(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((s): s is string => typeof s === "string");
  } catch {
    return [];
  }
}

function write(chain: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(chain));
  } catch {
    // Quota / private mode — swallow.
  }
}

export const breadcrumb = {
  chain: read,

  /** Replace the trail with a single-entry trail. Used on direct navigation. */
  reset(slug: string): string[] {
    const next = [slug];
    write(next);
    return next;
  },

  /** Clear the trail entirely (e.g. user clicked "← All canvases"). */
  clear(): void {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.removeItem(KEY);
    } catch {
      // ignore
    }
  },

  /**
   * Extend the trail with `slug`. If `slug` already appears, the trail is
   * truncated to and including that entry — i.e. the user navigated back
   * to an ancestor canvas via the link node.
   */
  enter(slug: string): string[] {
    const cur = read();
    const existing = cur.indexOf(slug);
    let next: string[];
    if (existing >= 0) {
      next = cur.slice(0, existing + 1);
    } else {
      next = [...cur, slug];
    }
    write(next);
    return next;
  },

  /** True if `slug` is anywhere in the current chain. */
  includes(slug: string): boolean {
    return read().includes(slug);
  },
};
