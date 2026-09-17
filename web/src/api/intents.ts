import { api } from "./client";

/**
 * The project-level intents queue API (#148 backend, #323 web surface).
 *
 * Wraps the same HTTP endpoints the MCP / CLI adapters mirror:
 *   - `GET  /api/intents`              -> pending intents (oldest first)
 *   - `GET  /api/intents/all`          -> every intent (newest first)
 *   - `POST /api/intents`              -> enqueue one
 *   - `POST /api/intents/{id}/resolve` -> mark one resolved with a result
 *
 * `create` authors the panel's free-text `user_request` kind: the payload
 * carries `{text}` plus, when the user attaches the selected canvas node as
 * the target, the same `{workspace_id, node_id}` node-ref shape
 * `drop_to_ingest` uses.
 */

export type IntentKind =
  | "drop_to_ingest"
  | "make_reference"
  | "attach_to_fact"
  | "user_request";

/** Mirrors the server's `Intent.to_dict()`. */
export type Intent = {
  id: string;
  kind: IntentKind | (string & {});
  origin_canvas_id: string | null;
  target: string | null;
  payload: Record<string, unknown>;
  status: "pending" | "resolved" | (string & {});
  created_at: number;
  resolved_at?: number;
  result?: Record<string, unknown>;
};

/**
 * Browser event dispatched after any intent mutate in this window (create
 * from the panel, dismiss). A UI-only nudge — same pattern as
 * `anchor:references-changed` — so the panel refetches immediately without
 * waiting for the SSE signal or the poll.
 */
export const INTENTS_CHANGED_EVENT = "anchor:intents-changed";

export function emitIntentsChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INTENTS_CHANGED_EVENT));
}

export const intents = {
  listPending: async () =>
    (await api.get<{ intents: Intent[]; count: number }>("/api/intents")).intents,
  listAll: async () =>
    (await api.get<{ intents: Intent[] }>("/api/intents/all")).intents,
  create: async (body: {
    text: string;
    workspaceSlug: string;
    nodeId?: string | null;
  }): Promise<Intent> => {
    const payload: Record<string, unknown> = { text: body.text };
    if (body.nodeId) {
      payload.workspace_id = body.workspaceSlug;
      payload.node_id = body.nodeId;
    }
    const res = await api.post<{ intent?: Intent; error?: string; message?: string }>(
      "/api/intents",
      {
        kind: "user_request",
        origin_canvas_id: body.workspaceSlug,
        payload,
      },
    );
    if (!res.intent) throw new Error(res.message ?? res.error ?? "intent create failed");
    emitIntentsChanged();
    return res.intent;
  },
  resolve: async (id: string, result?: Record<string, unknown>) => {
    const res = await api.post<{ resolved?: Intent; error?: string }>(
      `/api/intents/${id}/resolve`,
      result !== undefined ? { result } : {},
    );
    if (!res.resolved) throw new Error(res.error ?? "intent resolve failed");
    emitIntentsChanged();
    return res.resolved;
  },
};
