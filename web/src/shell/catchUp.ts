/**
 * Catch-up bookkeeping (#325): the per-canvas "last seen version" that
 * decides whether the "While you were away" panel shows.
 *
 * Storage is localStorage keyed per canvas slug. Every access is wrapped
 * in try/catch (same contract as uiStore's layout persistence): private
 * mode, jsdom, or blocked site data must degrade to "no memory" — the
 * canvas renders normally and the panel simply never shows.
 */

const KEY_PREFIX = "anchor.canvas.lastSeen.";

export function lastSeenKey(slug: string): string {
  return `${KEY_PREFIX}${slug}`;
}

/** The stored last-seen version for `slug`, or null when unknown. */
export function readLastSeen(slug: string): number | null {
  try {
    if (typeof window === "undefined") return null;
    const ls = window.localStorage;
    if (!ls || typeof ls.getItem !== "function") return null;
    const raw = ls.getItem(lastSeenKey(slug));
    if (raw === null) return null;
    const version = Number(raw);
    return Number.isFinite(version) && version >= 0 ? version : null;
  } catch {
    return null;
  }
}

/** Persist the last-seen version for `slug`. Failures are swallowed. */
export function writeLastSeen(slug: string, version: number): void {
  try {
    if (typeof window === "undefined") return;
    const ls = window.localStorage;
    if (!ls || typeof ls.setItem !== "function") return;
    ls.setItem(lastSeenKey(slug), String(version));
  } catch {
    // Private mode / quota — the panel just won't have a memory.
  }
}

/**
 * Show the panel only when we HAVE a memory of this canvas and its
 * version moved past it. A first visit (no stored value) records the
 * current version silently instead of announcing the whole history.
 */
export function shouldShowCatchUp(
  lastSeen: number | null,
  currentVersion: number,
): boolean {
  return lastSeen !== null && currentVersion > lastSeen;
}
