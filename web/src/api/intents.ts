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

/**
 * Where a thread item sits on the canvas, in canvas coordinates.
 *
 * Most items are lines in a conversation. A `message` with a place is a
 * ghost of work to come, drawn where the element will go; a `question` with a
 * place is asked beside the thing it is about.
 */
export type Place = { x: number; y: number; width?: number; height?: number };

/** A placed message's progress: grey and dotted, being worked on, landed. */
export type PlaceState = "planned" | "active" | "done";

/** One entry in an intent's thread. Mirrors the server's `ThreadItem`. */
export type ThreadItem = {
  id: string;
  type: "message" | "question" | "suggestion" | "result";
  author: { kind: string; label?: string | null; id?: string | null };
  text: string;
  created_at: number;
  state: string | null;
  answer?: string;
  ops?: Record<string, unknown>[];
  supersedes?: string;
  applied_versions?: number[];
  place?: Place;
  /** Question only: answers offered for one press; free text still answers. */
  options?: string[];
};

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
  targets?: { workspace_id: string; node_id: string }[];
  base_version?: number | null;
  items?: ThreadItem[];
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
    /**
     * Every node the request is about. A remark drawn on the canvas points at
     * what it rings, which is usually more than one thing -- `nodeId` can only
     * carry the single-target shape the free-text panel writes. Passing these
     * makes the intent a thread: the server anchors it to the selection and
     * records the canvas version it was written against, so the ask can still
     * be read in the state it was made about.
     */
    targets?: string[];
    /**
     * The drawing, read as nodes and edges before it left the browser.
     *
     * The words alone lose the shape of what was drawn: five labels arrive in
     * the order they were typed, every connector gone, so a child reads as a
     * sibling. This carries the structure and where each piece sat, which is
     * what lets an agent rebuild the thing that was actually sketched.
     */
    sketch?: unknown;
    /**
     * Lines drawn across cards, resolved to row boundaries in the browser:
     * `{node, after, afterIndex}`. "Split here" arrives as *where*.
     */
    cuts?: unknown;
    /**
     * Crosses drawn over edges, resolved in the browser to the edge struck
     * out: `{edge, source, target}`. "Remove this link" arrives as *which*.
     */
    strikes?: unknown;
    /**
     * Where each label's line starts, resolved in the browser to a card and,
     * on a table, a row: `{text, node, row, rowIndex, at}`. "Add +1" drawn
     * out of one cell arrives as *which value*.
     */
    pointers?: unknown;
  }): Promise<Intent> => {
    const payload: Record<string, unknown> = { text: body.text };
    if (body.sketch) payload.sketch = body.sketch;
    if (body.cuts) payload.cuts = body.cuts;
    if (body.strikes) payload.strikes = body.strikes;
    if (body.pointers) payload.pointers = body.pointers;
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
        ...(body.targets?.length
          ? {
              targets: body.targets.map((node_id) => ({
                workspace_id: body.workspaceSlug,
                node_id,
              })),
            }
          : {}),
      },
    );
    if (!res.intent) throw new Error(res.message ?? res.error ?? "intent create failed");
    emitIntentsChanged();
    return res.intent;
  },
  /** One intent with its whole thread. */
  get: async (id: string): Promise<Intent | null> => {
    const res = await api.get<{ intent?: Intent; error?: string }>(`/api/intents/${id}`);
    return res.intent ?? null;
  },
  /**
   * The thread verbs, as the canvas needs them. Approving and declining a
   * suggestion here is what lets the intent be the surface a proposal is
   * judged from, rather than a separate list somewhere else.
   */
  addItem: async (
    id: string,
    body: { type: ThreadItem["type"]; text?: string; place?: Place; options?: string[] },
  ): Promise<ThreadItem> => {
    const res = await api.post<{ item?: ThreadItem; error?: string; message?: string }>(
      `/api/intents/${id}/items`,
      body,
    );
    if (!res.item) throw new Error(res.message ?? res.error ?? "add item failed");
    emitIntentsChanged();
    return res.item;
  },
  updateItem: async (
    id: string,
    itemId: string,
    body: { text?: string; state?: PlaceState; place?: Place },
  ): Promise<ThreadItem> => {
    const res = await api.patch<{ item?: ThreadItem; error?: string; message?: string }>(
      `/api/intents/${id}/items/${itemId}`,
      body,
    );
    if (!res.item) throw new Error(res.message ?? res.error ?? "update item failed");
    emitIntentsChanged();
    return res.item;
  },
  answer: async (id: string, itemId: string, text: string): Promise<ThreadItem> => {
    const res = await api.post<{ item?: ThreadItem; error?: string; message?: string }>(
      `/api/intents/${id}/items/${itemId}/answer`,
      { text },
    );
    if (!res.item) throw new Error(res.message ?? res.error ?? "answer failed");
    emitIntentsChanged();
    return res.item;
  },
  apply: async (id: string, itemId: string): Promise<ThreadItem> => {
    const res = await api.post<{ item?: ThreadItem; error?: string; message?: string }>(
      `/api/intents/${id}/items/${itemId}/apply`,
      {},
    );
    if (!res.item) throw new Error(res.message ?? res.error ?? "apply failed");
    emitIntentsChanged();
    return res.item;
  },
  /**
   * Put an applied suggestion back. The other half of "act, then ask": an
   * agent that applied its change directly must leave the human a way to
   * undo it that is as cheap as approving would have been.
   */
  revert: async (id: string, itemId: string): Promise<ThreadItem> => {
    const res = await api.post<{ item?: ThreadItem; error?: string; message?: string }>(
      `/api/intents/${id}/items/${itemId}/revert`,
      {},
    );
    if (!res.item) throw new Error(res.message ?? res.error ?? "revert failed");
    emitIntentsChanged();
    return res.item;
  },
  decline: async (id: string, itemId: string, comment?: string): Promise<ThreadItem> => {
    const res = await api.post<{ item?: ThreadItem; error?: string; message?: string }>(
      `/api/intents/${id}/items/${itemId}/decline`,
      comment ? { comment } : {},
    );
    if (!res.item) throw new Error(res.message ?? res.error ?? "decline failed");
    emitIntentsChanged();
    return res.item;
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
