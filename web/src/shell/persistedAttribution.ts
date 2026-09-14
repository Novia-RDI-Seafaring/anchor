/**
 * Persisted per-node attribution (#325): who last touched a node,
 * answered from the event log rather than this session's SSE stream.
 *
 * The inspector's "edited by" chip prefers the live session answer
 * (`canvasStore.lastEditors`, #322) and falls back to this map for nodes
 * not touched while the tab was open. The map is fetched lazily — on the
 * first selection that needs it, never on canvas load — via the whole-log
 * `canvas_changes` fold (`since_version=0`), and cached per slug for the
 * session. Live edits keep winning through the session store, so the
 * cache staying static is fine.
 */
import { canvases, type ChangeActor } from "@/api/canvases";

const cache = new Map<string, Promise<Record<string, ChangeActor | null>>>();

/**
 * The per-node "last touched by" map for a canvas. One request per slug
 * per session; concurrent callers share the in-flight promise. A failed
 * fetch is evicted so a later selection can retry.
 */
export function getTouchedMap(
  slug: string,
): Promise<Record<string, ChangeActor | null>> {
  let promise = cache.get(slug);
  if (!promise) {
    promise = canvases
      .changes(slug, 0)
      .then((body) => body.touched ?? {})
      .catch((err) => {
        cache.delete(slug);
        throw err;
      });
    cache.set(slug, promise);
  }
  return promise;
}

/** Test helper: forget cached maps (all, or one slug). */
export function clearTouchedCache(slug?: string): void {
  if (slug === undefined) cache.clear();
  else cache.delete(slug);
}
