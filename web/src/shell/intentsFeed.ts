/**
 * intentsFeed — data layer for the Intents panel (#323).
 *
 * Pure helpers (split / titles / resolution text) plus the `useIntentsFeed`
 * hook that keeps the project's intent list live. The hook is mounted once by
 * FilesExplorer so the tab badge and the panel body share one feed.
 *
 * Liveness has three legs, matching the queue's push-notify / pull-payload
 * design and the other panels' habits:
 *   1. SSE — `GET /api/intents/events` fires an `intent_pending {count}`
 *      signal on every change made through the serving process; the hook
 *      refetches on each signal.
 *   2. Poll — a light 8s interval (the FilesExplorer cadence) reconciles
 *      changes the SSE cannot see: an agent resolving over stdio MCP or the
 *      CLI mutates the durable store from a different process.
 *   3. Local nudge — the `anchor:intents-changed` browser event fired by this
 *      window's own mutations (create / dismiss) refetches immediately.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { INTENTS_CHANGED_EVENT, intents, type Intent } from "@/api/intents";
import { IntentsSse } from "@/realtime/intentsSse";

/** How many resolved intents the "recently resolved" section keeps. */
export const RECENT_RESOLVED_LIMIT = 8;

/** Polling fallback cadence, ms — matches the FilesExplorer lists. */
export const INTENTS_POLL_MS = 8000;

/** Split the full list into open (oldest first — the queue order an agent
 *  drains) and recently resolved (newest first, capped). */
export function splitIntents(
  all: Intent[],
  recentLimit: number = RECENT_RESOLVED_LIMIT,
): { open: Intent[]; resolved: Intent[] } {
  const open = all
    .filter((i) => i.status === "pending")
    .sort((a, b) => a.created_at - b.created_at || a.id.localeCompare(b.id));
  const resolved = all
    .filter((i) => i.status === "resolved")
    .sort((a, b) => b.created_at - a.created_at || b.id.localeCompare(a.id))
    .slice(0, recentLimit);
  return { open, resolved };
}

/** Human label for an intent kind. Unknown kinds pass through humanized. */
const KIND_LABEL: Record<string, string> = {
  drop_to_ingest: "Ingest dropped document",
  make_reference: "Make reference",
  attach_to_fact: "Attach to fact",
  user_request: "Request",
};

export function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind.replace(/_/g, " ");
}

/** The row's primary line. A free-text request shows its text; a drop shows
 *  the dropped file; anything else falls back to the kind label. */
export function intentTitle(intent: Intent): string {
  if (intent.kind === "user_request") {
    const text = typeof intent.payload.text === "string" ? intent.payload.text.trim() : "";
    if (text) return text;
  }
  if (intent.kind === "drop_to_ingest") {
    const name = intent.payload.filename ?? intent.payload.slug;
    if (typeof name === "string" && name) return `Ingest ${name}`;
  }
  return kindLabel(intent.kind);
}

/** The attached target node id, when the payload carries the
 *  `{workspace_id, node_id}` node-ref shape. */
export function targetNodeId(intent: Intent): string | null {
  const id = intent.payload.node_id;
  return typeof id === "string" && id ? id : null;
}

/** Free-form resolution text off a resolved intent's `result`, when the
 *  record carries something human-readable. Preferred keys first; otherwise
 *  a compact JSON of whatever the agent recorded. */
export function resolutionText(intent: Intent): string | null {
  const result = intent.result;
  if (!result) return null;
  for (const key of ["note", "message", "summary", "status", "error", "produced_slug"]) {
    const v = result[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  if (result.dismissed === true) return "dismissed";
  const keys = Object.keys(result);
  if (keys.length === 0) return null;
  try {
    const compact = JSON.stringify(result);
    return compact.length > 120 ? `${compact.slice(0, 117)}…` : compact;
  } catch (_err) {
    return null;
  }
}

/** Compact relative age for a server timestamp (epoch seconds). */
export function timeAgo(ts: number, nowMs: number = Date.now()): string {
  if (!ts) return "";
  const secs = Math.max(0, Math.floor(nowMs / 1000 - ts));
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export type IntentsFeed = {
  /** Every intent (pending + resolved), newest first, as the server returns. */
  items: Intent[];
  open: Intent[];
  resolved: Intent[];
  openCount: number;
  error: string | null;
  refresh: () => Promise<void>;
};

export function useIntentsFeed(): IntentsFeed {
  const [items, setItems] = useState<Intent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setItems(await intents.listAll());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();

    // Push: the SSE count signal (fires an immediate snapshot on connect).
    const sse = new IntentsSse({ onPending: () => void refresh() });
    sse.connect();

    // Pull fallback: reconcile cross-process mutations (MCP stdio / CLI).
    const pollId = window.setInterval(() => void refresh(), INTENTS_POLL_MS);

    // Same-window nudge after our own create / dismiss.
    const onChanged = () => void refresh();
    window.addEventListener(INTENTS_CHANGED_EVENT, onChanged);

    return () => {
      sse.disconnect();
      window.clearInterval(pollId);
      window.removeEventListener(INTENTS_CHANGED_EVENT, onChanged);
    };
  }, [refresh]);

  const { open, resolved } = useMemo(() => splitIntents(items), [items]);
  return { items, open, resolved, openCount: open.length, error, refresh };
}
