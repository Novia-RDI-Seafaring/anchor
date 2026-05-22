/**
 * useWorkspacesList — shared, process-wide cache of the workspace envelope.
 *
 * The SubCanvasPrimitive needs per-child counts (`node_count`, `edge_count`)
 * + reference info but should NOT fetch the child workspace's full state
 * for every tile. The backend's `GET /api/workspaces` envelope already
 * carries everything; this hook caches the result so all sub-canvas tiles
 * on a page share one network call.
 *
 * Caching is intentionally simple — a module-scoped Promise + result,
 * refreshable via `refreshWorkspaces()`. Components subscribe via a tiny
 * `useSyncExternalStore`-style listener set so a refresh fans out to
 * every visible tile.
 */
import { useEffect, useState } from "react";

import { canvases, type WorkspaceListEntry } from "@/api/canvases";

type Snapshot = {
  items: WorkspaceListEntry[];
  bySlug: Map<string, WorkspaceListEntry>;
};

let cached: Snapshot | null = null;
let inflight: Promise<Snapshot> | null = null;
const listeners = new Set<(s: Snapshot) => void>();

function buildSnapshot(items: WorkspaceListEntry[]): Snapshot {
  const bySlug = new Map<string, WorkspaceListEntry>();
  for (const it of items) bySlug.set(it.slug, it);
  return { items, bySlug };
}

async function fetchSnapshot(): Promise<Snapshot> {
  if (inflight) return inflight;
  inflight = canvases
    .list()
    .then((items) => {
      cached = buildSnapshot(items);
      inflight = null;
      for (const fn of listeners) fn(cached);
      return cached;
    })
    .catch((err) => {
      inflight = null;
      throw err;
    });
  return inflight;
}

/** Force a re-fetch — used when a sub-canvas is created or removed. */
export function refreshWorkspaces(): Promise<Snapshot> {
  cached = null;
  return fetchSnapshot();
}

/**
 * Subscribe to the workspaces envelope. Returns the current snapshot
 * (cached or freshly-fetched) and re-renders when the cache updates.
 */
export function useWorkspacesList(): Snapshot | null {
  const [snap, setSnap] = useState<Snapshot | null>(cached);
  useEffect(() => {
    let active = true;
    listeners.add(setSnap);
    if (cached) {
      setSnap(cached);
    } else {
      fetchSnapshot()
        .then((s) => {
          if (active) setSnap(s);
        })
        .catch(() => {
          /* swallow — UI shows fallback */
        });
    }
    return () => {
      active = false;
      listeners.delete(setSnap);
    };
  }, []);
  return snap;
}

/** Get a single entry without subscribing — for one-shot reads. */
export function getWorkspaceEntry(slug: string): WorkspaceListEntry | undefined {
  return cached?.bySlug.get(slug);
}
